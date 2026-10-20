#!/usr/bin/env python3
"""
iSilo Recovery v2.0 - Windows PDB Reader with Hyperlink Support
Developer: seriusman0@gmail.com

Supported:
  - iSilo 3.x / 4-6.x SilX (full HTML render + hyperlinks)
  - iSilo SDoc (metadata + index)
  - PalmDOC (plain text)
"""
import sys, struct, zlib, os, re, webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font as tkfont

# ─────────────────────────── PDB PARSER ────────────────────────────

def u16(d, o): return struct.unpack('>H', d[o:o+2])[0]
def u32(d, o): return struct.unpack('>I', d[o:o+4])[0]

class PdbDoc:
    def __init__(self, path):
        self.path = path
        self.data = open(path, 'rb').read()
        self._parse()

    def _parse(self):
        d = self.data
        if len(d) < 78: raise ValueError(f"Too small: {len(d)} bytes")
        nb = d[0:32]; ne = nb.find(0)
        self.name    = nb[:ne if ne>=0 else 32].decode('latin-1', errors='replace').strip()
        self.db_type = d[60:64].decode('latin-1', errors='replace')
        self.creator = d[64:68].decode('latin-1', errors='replace')
        self.nrec    = u16(d, 76)
        try:
            import datetime
            self.created = datetime.datetime(1904,1,1) + datetime.timedelta(seconds=u32(d,36))
        except:
            self.created = None
        offs = [u32(d, 78+i*8) for i in range(self.nrec)]
        self.records = [d[offs[i]:offs[i+1] if i+1<self.nrec else len(d)] for i in range(self.nrec)]
        if   self.creator=='iSil' and self.db_type=='SilX': self.format='iSilo 4-6.x (SilX)'
        elif self.creator=='iSil' and self.db_type=='iSil': self.format='iSilo 3.x'
        elif self.creator=='REAd' and self.db_type=='TEXt': self.format='PalmDOC'
        elif self.creator=='SilX' and self.db_type=='SDoc': self.format='iSilo SDoc (SilX)'
        else: self.format=f'Palm DB ({self.db_type}/{self.creator})'

    def extract_html(self):
        """Return list of (html_str, page_index) tuples - one per compressed block."""
        if 'PalmDOC' in self.format:
            return [('<pre>' + self._palmDoc() + '</pre>', 0)]
        if 'SDoc' in self.format:
            return [('<pre>' + self._sdoc_summary() + '</pre>', 0)]
        return self._silx_pages()

    def _silx_pages(self):
        """Decompress SilX records → list of HTML page strings."""
        pages = []
        for i, rec in enumerate(self.records[1:], 1):
            html = self._try_decompress(rec)
            if html:
                pages.append((html, i))
        if not pages:
            # Fallback: raw text
            return [('<pre>' + self._extract_raw() + '</pre>', 0)]
        return pages

    def _try_decompress(self, rec):
        for start in range(0, min(len(rec), 12)):
            try:
                dec = zlib.decompress(rec[start:])
                if len(dec) < 10: continue
                try:   text = dec.decode('utf-8')
                except: text = dec.decode('latin-1', errors='replace')
                if self._looks_html(text) or self._looks_text(text):
                    return text
            except: pass
        # Raw text fallback
        if self._looks_text_bytes(rec):
            try:    return rec.decode('utf-8', errors='replace')
            except: return rec.decode('latin-1', errors='replace')
        return None

    def _palmDoc(self):
        if not self.records: return ''
        r0 = self.records[0]
        comp = u16(r0,0) if len(r0)>=2 else 1
        buf = []
        for rec in self.records[1:]:
            if comp==2: buf.append(self._lz77(rec).decode('latin-1','replace'))
            else:        buf.append(rec.decode('latin-1','replace'))
        return ''.join(buf)

    def _lz77(self, data):
        out=[]
        i=0
        while i<len(data):
            c=data[i]; i+=1
            if c==0: out.append(0)
            elif c<=8:
                for _ in range(c):
                    if i<len(data): out.append(data[i]); i+=1
            elif c<=0x7F: out.append(c)
            elif c<=0xBF:
                if i>=len(data): break
                n=data[i]; i+=1
                dist=(c&0x3F)<<8|n; length=(dist&7)+3; offset=(dist>>3)&0x1FFF
                s=len(out)-offset
                for j in range(length): out.append(out[s+j] if 0<=s+j<len(out) else 0x20)
            else: out.append(0x20); out.append(c^0x80)
        return bytes(out)

    def _sdoc_summary(self):
        sz = os.path.getsize(self.path)
        sep = '='*50
        lines = [sep,
            '  iSilo Recovery - Document Information', sep, '',
            f'  Title   : {self.name}',
            f'  Format  : {self.format}',
            f'  Type    : {self.db_type} / Creator: {self.creator}',
            f'  Records : {self.nrec:,}',
            f'  Size    : {sz:,} bytes ({sz/1024/1024:.2f} MB)',
        ]
        if self.created:
            try: lines.append(f'  Created : {self.created.strftime("%Y-%m-%d")}')
            except: pass
        lines += ['', sep, '',
            '  FORMAT NOTE:',
            '  This document uses iSilo SDoc proprietary format.',
            '  Full text requires the original iSilo engine.',
            '', sep, '']
        toc = self._extract_toc()
        if toc: lines.append(toc)
        return '\n'.join(lines)

    def _extract_toc(self):
        buf = []
        for rec in self.records[-5:]:
            for e in rec.split(b'\x00'):
                if len(e)<8: continue
                clean = e.replace(b'\xa0', b' ').decode('latin-1','replace')
                clean = re.sub(r'[^\x20-\x7e\n\t]','',clean).strip()
                if len(clean)<5: continue
                weird = sum(1 for c in clean if c in '{}[]~^`|\\<>*_=+')
                if weird>1: continue
                if not re.search(r'[a-zA-Z]{3,}', clean): continue
                buf.append(clean)
        return '\n'.join(buf)

    def _extract_raw(self):
        out=[]
        for rec in self.records[1:20]:
            out.append(''.join(chr(b) if 32<=b<127 or b in(9,10,13) else ' ' for b in rec))
        return '\n'.join(out)

    @staticmethod
    def _looks_html(s):
        return bool(re.search(r'<(html|body|p|h[1-6]|div|ul|li|a)\b', s, re.I))

    @staticmethod
    def _looks_text(s):
        if not s: return False
        p = sum(1 for c in s[:200] if c.isprintable() or c in '\t\n\r')
        return p > len(s[:200])*0.6

    @staticmethod
    def _looks_text_bytes(d):
        if not d: return False
        s = d[:200]
        p = sum(1 for b in s if 32<=b<127 or b in(9,10,13))
        return p > len(s)*0.7


# ─────────────────────────── HTML PARSER ───────────────────────────

class Token:
    __slots__ = ('kind','name','attrs','text')
    def __init__(self, kind, name='', attrs=None, text=''):
        self.kind=kind; self.name=name
        self.attrs=attrs or {}; self.text=text

def parse_html(html_text):
    """Parse HTML → list[Token]"""
    tokens = []
    pos = 0
    unescape = lambda t: (t.replace('&amp;','&').replace('&lt;','<')
        .replace('&gt;','>').replace('&quot;','"')
        .replace('&nbsp;','\u00a0').replace('&#160;','\u00a0')
        .replace('&apos;',"'"))

    while pos < len(html_text):
        ts = html_text.find('<', pos)
        if ts < 0:
            raw = html_text[pos:]
            if raw: tokens.append(Token('text', text=unescape(raw)))
            break
        if ts > pos:
            raw = html_text[pos:ts]
            tokens.append(Token('text', text=unescape(raw)))
        te = html_text.find('>', ts)
        if te < 0:
            break
        tag = html_text[ts+1:te].strip()
        pos = te+1
        if not tag or tag.startswith('!') or tag.startswith('?'):
            continue
        if tag.startswith('/'):
            tokens.append(Token('close', name=tag[1:].strip().lower().split()[0]))
            continue
        parts = tag.split(None, 1)
        tn = parts[0].lower().rstrip('/')
        attrs = {}
        if len(parts) > 1:
            for m in re.finditer(r'([\w-]+)\s*=\s*"([^"]*)"|([\w-]+)\s*=\s*\'([^\']*)\'|([\w-]+)\s*=\s*(\S+)|([\w-]+)', parts[1]):
                if   m.group(1): attrs[m.group(1).lower()] = m.group(2)
                elif m.group(3): attrs[m.group(3).lower()] = m.group(4)
                elif m.group(5): attrs[m.group(5).lower()] = m.group(6)
                elif m.group(7): attrs[m.group(7).lower()] = ''
        tokens.append(Token('open', name=tn, attrs=attrs))
    return tokens


# ─────────────────────────── HTML TEXT WIDGET ──────────────────────

LINK_COLOR  = '#1565C0'
LINK_HOVER  = '#0D47A1'
VISITED_COL = '#6A1B9A'

class HtmlTextWidget(tk.Text):
    """tkinter.Text that renders basic HTML with clickable hyperlinks."""

    def __init__(self, master, on_link=None, dark=False, **kw):
        self._dark = dark
        self._on_link = on_link  # callback(href, link_text)
        bg = '#1E1E2E' if dark else '#FAFAFA'
        fg = '#E0E0E0' if dark else '#1A1A2E'
        super().__init__(master, bg=bg, fg=fg,
                         relief='flat', wrap='word',
                         padx=20, pady=16,
                         spacing1=2, spacing2=3,
                         cursor='arrow', state='disabled', **kw)
        self._setup_tags()
        self._anchors = {}   # anchor_name → text_index
        self._link_regions = []  # list of (start_idx, end_idx, href, text)
        self.bind('<Motion>', self._on_motion)
        self.bind('<Button-1>', self._on_click)
        self._last_link = None

    def _setup_tags(self):
        dark = self._dark
        base_fg = '#E0E0E0' if dark else '#1A1A2E'
        heading_fg = '#FFFFFF' if dark else '#1A237E'
        link_fg = '#64B5F6' if dark else LINK_COLOR
        link_hover = '#90CAF9' if dark else LINK_HOVER
        visited_fg = '#CE93D8' if dark else VISITED_COL
        code_bg  = '#2D2D3D' if dark else '#F5F5F5'

        self.tag_configure('h1',   font=('Segoe UI', 18, 'bold'),  foreground=heading_fg, spacing1=10, spacing3=4)
        self.tag_configure('h2',   font=('Segoe UI', 15, 'bold'),  foreground=heading_fg, spacing1=8,  spacing3=3)
        self.tag_configure('h3',   font=('Segoe UI', 13, 'bold'),  foreground=heading_fg, spacing1=6,  spacing3=2)
        self.tag_configure('h4',   font=('Segoe UI', 12, 'bold'),  foreground=heading_fg, spacing1=4)
        self.tag_configure('h5',   font=('Segoe UI', 11, 'bold'),  foreground=heading_fg)
        self.tag_configure('h6',   font=('Segoe UI', 10, 'bold'),  foreground=heading_fg)
        self.tag_configure('bold', font=('Segoe UI',  self._fs(), 'bold'))
        self.tag_configure('italic', font=('Segoe UI', self._fs(), 'italic'))
        self.tag_configure('code', font=('Courier New', self._fs()-1), background=code_bg)
        self.tag_configure('li_bullet', lmargin1=20, lmargin2=32)
        self.tag_configure('link',       foreground=link_fg,    underline=True, font=('Segoe UI', self._fs()))
        self.tag_configure('link_hover', foreground=link_hover, underline=True, font=('Segoe UI', self._fs()), relief='raised')
        self.tag_configure('link_visited',foreground=visited_fg,underline=True, font=('Segoe UI', self._fs()))
        self.tag_configure('center',  justify='center')
        self.tag_configure('pre',     font=('Courier New', self._fs()-1), background=code_bg, wrap='none')

    def _fs(self):
        return getattr(self, '_font_size', 13)

    def set_font_size(self, pt):
        self._font_size = pt
        # Reconfigure tag fonts
        self._setup_tags()
        self.configure(font=('Segoe UI', pt))

    def render(self, html_pages, page_idx=0):
        """Render a list of HTML page strings (multi-record document)."""
        self._anchors.clear()
        self._link_regions.clear()
        self._visited = getattr(self, '_visited', set())

        self.configure(state='normal')
        self.delete('1.0', 'end')

        for page_html, _ in html_pages:
            tokens = parse_html(page_html)
            self._render_tokens(tokens)

        self.configure(state='disabled')

    def _render_tokens(self, tokens):
        stack = []    # active tags
        in_body = False
        skip_tags = {'html','head','title','style','script','meta'}

        for tok in tokens:
            if tok.kind == 'open':
                tn = tok.name
                if tn in skip_tags and tn != 'body':
                    if tn in ('style','script'):
                        stack.append(tn)  # push to skip content
                    continue
                if tn == 'body':
                    in_body = True
                    continue
                if not in_body and tn not in ('h1','h2','h3','h4','h5','h6','p','div','ul','ol','li','a','b','strong','i','em','br','hr','pre','code','table','tr','td','th','span'):
                    continue

                if tn == 'br':
                    self._insert('\n')
                elif tn == 'hr':
                    self._insert('\n' + '─'*60 + '\n')
                elif tn in ('h1','h2','h3','h4','h5','h6'):
                    self._insert('\n')
                    stack.append(tn)
                elif tn == 'p':
                    self._insert('\n')
                    stack.append(tn)
                elif tn in ('ul','ol'):
                    self._insert('\n')
                    stack.append(tn)
                elif tn == 'li':
                    bullet = '• ' if 'ul' in stack else f'{len([x for x in stack if x=="li"])+1}. '
                    self._insert('\n' + bullet)
                    stack.append('li')
                elif tn == 'a':
                    href = tok.attrs.get('href','')
                    name = tok.attrs.get('name','') or tok.attrs.get('id','')
                    if name:
                        # Register anchor position
                        idx = self.index('insert')
                        self._anchors[name] = idx
                    if href:
                        stack.append(('a', href))
                        # Mark link start
                        start_idx = self.index('insert')
                        stack.append(('link_start', start_idx, href))
                elif tn in ('b','strong'):
                    stack.append('bold')
                elif tn in ('i','em'):
                    stack.append('italic')
                elif tn == 'code':
                    stack.append('code')
                elif tn == 'pre':
                    self._insert('\n')
                    stack.append('pre')
                elif tn in ('div','blockquote','section','article'):
                    self._insert('\n')
                    stack.append(tn)
                elif tn in ('table','tr'):
                    self._insert('\n')
                    stack.append(tn)
                elif tn in ('td','th'):
                    self._insert('\t')
                    stack.append(tn)
                elif tn in ('span','font'):
                    stack.append(tn)
                # id/name anchors on any element
                anchor_id = tok.attrs.get('id','') or tok.attrs.get('name','')
                if anchor_id and tn not in ('a',):
                    self._anchors[anchor_id] = self.index('insert')

            elif tok.kind == 'close':
                tn = tok.name
                if stack and stack[-1] in ('style','script'):
                    stack.pop()
                    continue

                # Check for link end
                while stack:
                    top = stack[-1]
                    if isinstance(top, tuple) and top[0] == 'link_start':
                        stack.pop()
                        start_idx, href = top[1], top[2]
                        end_idx = self.index('insert')
                        # Apply link tags
                        visited = href in getattr(self, '_visited', set())
                        tag = 'link_visited' if visited else 'link'
                        self.tag_add(tag, start_idx, end_idx)
                        # Also add a unique tag per link for click detection
                        link_tag = f'link_{len(self._link_regions)}'
                        self.tag_add(link_tag, start_idx, end_idx)
                        self._link_regions.append((start_idx, end_idx, href, link_tag))
                        break
                    break

                if tn in ('h1','h2','h3','h4','h5','h6','p','ul','ol','li','div',
                          'blockquote','pre','section','article','table','tr','td','th'):
                    self._insert('\n')
                    # Remove from stack
                    for i in range(len(stack)-1, -1, -1):
                        if stack[i] == tn:
                            stack.pop(i); break

                elif tn in ('b','strong','i','em','code','span','font','a'):
                    for i in range(len(stack)-1, -1, -1):
                        if stack[i] == tn or (isinstance(stack[i], tuple) and stack[i][0] == tn):
                            stack.pop(i); break

            elif tok.kind == 'text':
                if stack and stack[-1] in ('style','script'):
                    continue
                txt = tok.text
                # Clean up excessive whitespace (but preserve newlines in pre)
                if not ('pre' in stack):
                    txt = re.sub(r'\n\s*\n', '\n', txt)
                    txt = re.sub(r'[ \t]+', ' ', txt)
                
                # Determine tags to apply
                apply_tags = []
                for s in stack:
                    if isinstance(s, str) and s in ('h1','h2','h3','h4','h5','h6','bold','italic','code','pre','li_bullet'):
                        apply_tags.append(s)
                    elif isinstance(s, str) and s.startswith('h') and len(s)==2 and s[1].isdigit():
                        apply_tags.append(s)
                
                self._insert(txt, *apply_tags)

    def _insert(self, text, *tags):
        self.insert('end', text, tags if tags else ())

    def scroll_to_anchor(self, anchor):
        """Scroll to anchor position."""
        if anchor in self._anchors:
            self.see(self._anchors[anchor])
            return True
        # Try case-insensitive match
        al = anchor.lower()
        for k, v in self._anchors.items():
            if k.lower() == al:
                self.see(v)
                return True
        return False

    def _on_motion(self, event):
        idx = self.index(f'@{event.x},{event.y}')
        link = self._get_link_at(idx)
        if link != self._last_link:
            if self._last_link:
                # Restore old link appearance
                old_href, old_tag = self._last_link
                visited = old_href in getattr(self, '_visited', set())
                self.tag_remove('link_hover', '1.0', 'end')
            if link:
                href, tag = link
                self.configure(cursor='hand2')
                self.tag_add('link_hover', *self._get_tag_range(tag))
            else:
                self.configure(cursor='arrow')
            self._last_link = link

    def _on_click(self, event):
        idx = self.index(f'@{event.x},{event.y}')
        link = self._get_link_at(idx)
        if link and self._on_link:
            href, tag = link
            # Mark as visited
            if not hasattr(self, '_visited'): self._visited = set()
            self._visited.add(href)
            self.tag_remove('link', '1.0', 'end')
            for (s, e, h, lt) in self._link_regions:
                if h in self._visited:
                    self.tag_add('link_visited', s, e)
                else:
                    self.tag_add('link', s, e)
            # Find link text
            link_text = ''
            for (s, e, h, lt) in self._link_regions:
                if lt == tag:
                    link_text = self.get(s, e)
                    break
            self._on_link(href, link_text)

    def _get_link_at(self, idx):
        for (s, e, href, tag) in self._link_regions:
            try:
                if self.compare(idx, '>=', s) and self.compare(idx, '<', e):
                    return (href, tag)
            except:
                pass
        return None

    def _get_tag_range(self, tag):
        try:
            s = self.tag_ranges(tag)
            if s: return (s[0], s[1])
        except: pass
        return ('1.0', '1.0')


# ─────────────────────────── MAIN APP ──────────────────────────────

class IsiloRecoveryApp:
    APP_NAME = 'iSilo Recovery'
    VERSION  = '2.0.0'
    AUTHOR   = 'seriusman0@gmail.com'
    BG       = '#1A237E'
    FG       = '#FFFFFF'

    def __init__(self, root):
        self.root = root
        self.root.title(self.APP_NAME)
        self.root.geometry('1100x720')
        self.root.configure(bg=self.BG)
        self.docs      = []
        self.current   = None
        self._pages    = []    # current doc HTML pages
        self._page_idx = 0
        self._dark     = False
        self._fs       = 13
        self._history  = []    # navigation history [(doc, page, scroll)]
        self._fwd_hist = []
        self._build_ui()

    def _build_ui(self):
        # ── Top bar ──
        bar = tk.Frame(self.root, bg=self.BG, pady=8)
        bar.pack(fill='x')
        tk.Label(bar, text=f'\U0001F4D6  {self.APP_NAME}',
                 bg=self.BG, fg=self.FG, font=('Segoe UI',16,'bold')).pack(side='left', padx=16)
        tk.Label(bar, text='Read iSilo .pdb  free, no subscription',
                 bg=self.BG, fg='#90CAF9', font=('Segoe UI',10)).pack(side='left')
        tk.Button(bar, text='Open .pdb', command=self._open,
                  bg='#283593', fg=self.FG, relief='flat', padx=12, pady=4,
                  font=('Segoe UI',10,'bold'), cursor='hand2').pack(side='right', padx=16)
        tk.Button(bar, text='About', command=self._about,
                  bg=self.BG, fg='#90CAF9', relief='flat', padx=8,
                  font=('Segoe UI',9), cursor='hand2').pack(side='right')

        # ── Main pane ──
        pane = tk.PanedWindow(self.root, orient='horizontal', bg='#E0E0E0', sashwidth=4)
        pane.pack(fill='both', expand=True)

        # Left: library
        left = tk.Frame(pane, bg='#E8EAF6', width=220)
        pane.add(left, minsize=160)
        tk.Label(left, text='Library', bg='#E8EAF6', fg='#283593',
                 font=('Segoe UI',11,'bold')).pack(pady=(10,4), padx=10, anchor='w')
        self.lb = tk.Listbox(left, bg='white', fg='#1A237E',
                              selectbackground='#1A237E', selectforeground='white',
                              font=('Segoe UI',10), relief='flat', activestyle='none', borderwidth=0)
        self.lb.pack(fill='both', expand=True, padx=6, pady=(0,6))
        self.lb.bind('<<ListboxSelect>>', self._on_select)
        sb = ttk.Scrollbar(left, command=self.lb.yview)
        self.lb.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        tk.Button(left, text='Remove', command=self._remove,
                  bg='#EF9A9A', fg='#B71C1C', relief='flat',
                  font=('Segoe UI',9), cursor='hand2', pady=2).pack(padx=6, pady=4)

        # Right: reader
        right = tk.Frame(pane, bg='white')
        pane.add(right, minsize=500)

        # Navigation + toolbar
        nav = tk.Frame(right, bg='#ECEFF1', pady=3)
        nav.pack(fill='x')

        # Back / Forward buttons
        self.btn_back = tk.Button(nav, text='◀', command=self._go_back,
                                   relief='flat', bg='#ECEFF1', font=('Segoe UI',11),
                                   cursor='hand2', state='disabled', padx=6)
        self.btn_back.pack(side='left', padx=2)
        self.btn_fwd = tk.Button(nav, text='▶', command=self._go_forward,
                                  relief='flat', bg='#ECEFF1', font=('Segoe UI',11),
                                  cursor='hand2', state='disabled', padx=6)
        self.btn_fwd.pack(side='left', padx=2)

        # Page navigation
        self.btn_prev_page = tk.Button(nav, text='◁ Prev', command=self._prev_page,
                                        relief='flat', bg='#ECEFF1', font=('Segoe UI',9),
                                        cursor='hand2', state='disabled')
        self.btn_prev_page.pack(side='left', padx=4)
        self.lbl_page = tk.Label(nav, text='', bg='#ECEFF1', fg='#546E7A',
                                  font=('Segoe UI',9))
        self.lbl_page.pack(side='left')
        self.btn_next_page = tk.Button(nav, text='Next ▷', command=self._next_page,
                                        relief='flat', bg='#ECEFF1', font=('Segoe UI',9),
                                        cursor='hand2', state='disabled')
        self.btn_next_page.pack(side='left', padx=4)

        # Font size
        tk.Button(nav, text='-A', command=lambda: self._resize(-1),
                  relief='flat', bg='#ECEFF1', cursor='hand2').pack(side='right', padx=2)
        tk.Button(nav, text='+A', command=lambda: self._resize(1),
                  relief='flat', bg='#ECEFF1', cursor='hand2').pack(side='right', padx=2)
        # Dark mode
        self.btn_dark = tk.Button(nav, text='🌙', command=self._toggle_dark,
                                   relief='flat', bg='#ECEFF1', cursor='hand2', font=('Segoe UI',11))
        self.btn_dark.pack(side='right', padx=2)
        # Save
        tk.Button(nav, text='Save .txt', command=self._save,
                  relief='flat', bg='#283593', fg='white',
                  font=('Segoe UI',9), cursor='hand2', padx=6).pack(side='right', padx=4)
        # Copy
        tk.Button(nav, text='Copy', command=self._copy,
                  relief='flat', bg='#ECEFF1', font=('Segoe UI',9), cursor='hand2').pack(side='right', padx=2)

        # Info bar
        self.lbl_info = tk.Label(right, text='Open a .pdb file to begin',
                                  bg='#E3F2FD', fg='#1565C0', font=('Segoe UI',9),
                                  anchor='w', padx=10, pady=4)
        self.lbl_info.pack(fill='x')

        # HTML text widget with scrollbar
        txt_frame = tk.Frame(right, bg='white')
        txt_frame.pack(fill='both', expand=True)

        vscroll = ttk.Scrollbar(txt_frame, orient='vertical')
        self.html_view = HtmlTextWidget(
            txt_frame,
            on_link=self._handle_link,
            dark=self._dark,
            font=('Segoe UI', self._fs),
            yscrollcommand=vscroll.set,
        )
        vscroll.configure(command=self.html_view.yview)
        vscroll.pack(side='right', fill='y')
        self.html_view.pack(fill='both', expand=True)

        # Status bar
        self.status = tk.Label(self.root, text='Ready', bg='#283593', fg='white',
                                font=('Segoe UI',9), anchor='w', pady=3)
        self.status.pack(fill='x', side='bottom')

    # ── Navigation ──

    def _handle_link(self, href, link_text):
        """Handle hyperlink click - mirror iSilo behavior."""
        href = href.strip()
        self._set_status(f'Link: {href}')

        if href.startswith('#'):
            # Internal anchor navigation
            anchor = href[1:]
            if not self.html_view.scroll_to_anchor(anchor):
                self._set_status(f'Anchor not found: {anchor}')
            return

        if href.startswith(('http://', 'https://', 'ftp://')):
            # External web link - show dialog like iSilo
            self._show_web_link_dialog(href)
            return

        if href.startswith('mailto:'):
            # Email link
            self._show_email_link_dialog(href)
            return

        if href.startswith('tel:'):
            # Phone link
            self._show_tel_link_dialog(href)
            return

        if href.endswith('.pdb') or href.endswith('.PDB'):
            # Link to another document in same directory
            base_dir = Path(self.current.path).parent
            target = base_dir / href
            if target.exists():
                self._open_file(str(target))
            else:
                messagebox.showinfo('External Document',
                    f'The linked document was not found:\n{href}\n\n'
                    f'Make sure it is in the same folder as the current document.')
            return

        # Unknown link type
        self._set_status(f'Unresolved link: {href}')
        messagebox.showwarning('Unresolved Link',
            f'The hyperlink does not resolve to any known location:\n{href}')

    def _show_web_link_dialog(self, url):
        """Mimic iSilo web link dialog - tap URL to open browser."""
        dlg = tk.Toplevel(self.root)
        dlg.title('Web Link')
        dlg.geometry('420x160')
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(dlg, text='Tap the URL to open it in a web browser:',
                 font=('Segoe UI',10), pady=10).pack()

        url_var = tk.StringVar(value=url)
        entry = tk.Entry(dlg, textvariable=url_var, font=('Segoe UI',10),
                         fg=LINK_COLOR, cursor='hand2', relief='flat',
                         bg='#F5F5F5', width=50)
        entry.pack(padx=20, pady=4)
        entry.bind('<Button-1>', lambda e: (webbrowser.open(url), dlg.destroy()))

        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=10)
        tk.Button(btn_frame, text='Open in Browser',
                  command=lambda: (webbrowser.open(url), dlg.destroy()),
                  bg='#1A237E', fg='white', relief='flat', padx=12, pady=4,
                  cursor='hand2').pack(side='left', padx=4)
        tk.Button(btn_frame, text='Cancel', command=dlg.destroy,
                  relief='flat', padx=10).pack(side='left', padx=4)

    def _show_email_link_dialog(self, mailto_url):
        """Mimic iSilo email link dialog."""
        addr = mailto_url[7:] if mailto_url.startswith('mailto:') else mailto_url
        dlg = tk.Toplevel(self.root)
        dlg.title('Email Link')
        dlg.geometry('400x150')
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(dlg, text='Tap the email address to start your mail app:',
                 font=('Segoe UI',10), pady=10).pack()

        entry = tk.Entry(dlg, font=('Segoe UI',10), fg=LINK_COLOR,
                         cursor='hand2', relief='flat', bg='#F5F5F5', width=45)
        entry.insert(0, addr)
        entry.pack(padx=20, pady=4)
        entry.bind('<Button-1>', lambda e: (webbrowser.open(mailto_url), dlg.destroy()))

        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=8)
        tk.Button(btn_frame, text='Open Mail App',
                  command=lambda: (webbrowser.open(mailto_url), dlg.destroy()),
                  bg='#1A237E', fg='white', relief='flat', padx=12, pady=4,
                  cursor='hand2').pack(side='left', padx=4)
        tk.Button(btn_frame, text='Cancel', command=dlg.destroy,
                  relief='flat', padx=10).pack(side='left', padx=4)

    def _show_tel_link_dialog(self, tel_url):
        """Mimic iSilo phone link dialog."""
        num = tel_url[4:] if tel_url.startswith('tel:') else tel_url
        dlg = tk.Toplevel(self.root)
        dlg.title('Phone Link')
        dlg.geometry('380x150')
        dlg.resizable(False, False)
        dlg.grab_set()

        tk.Label(dlg, text='Phone number:',
                 font=('Segoe UI',10), pady=10).pack()

        entry = tk.Entry(dlg, font=('Segoe UI',12,'bold'), fg='#1A237E',
                         relief='flat', bg='#F5F5F5', width=30, justify='center')
        entry.insert(0, num)
        entry.pack(padx=20, pady=4)

        btn_frame = tk.Frame(dlg)
        btn_frame.pack(pady=8)
        tk.Button(btn_frame, text='Call', command=lambda: (webbrowser.open(tel_url), dlg.destroy()),
                  bg='#2E7D32', fg='white', relief='flat', padx=20, pady=4, cursor='hand2').pack(side='left', padx=4)
        tk.Button(btn_frame, text='Cancel', command=dlg.destroy,
                  relief='flat', padx=10).pack(side='left', padx=4)

    # ── History ──

    def _push_history(self):
        if self.current:
            yview = self.html_view.yview()[0]
            self._history.append((self.current.path, self._page_idx, yview))
            self._fwd_hist.clear()
            self._update_nav_buttons()

    def _go_back(self):
        if not self._history: return
        yview = self.html_view.yview()[0]
        self._fwd_hist.append((self.current.path if self.current else None, self._page_idx, yview))
        path, page, scroll = self._history.pop()
        self._open_file(path, page_idx=page, scroll=scroll, push_hist=False)
        self._update_nav_buttons()

    def _go_forward(self):
        if not self._fwd_hist: return
        yview = self.html_view.yview()[0]
        self._history.append((self.current.path if self.current else None, self._page_idx, yview))
        path, page, scroll = self._fwd_hist.pop()
        self._open_file(path, page_idx=page, scroll=scroll, push_hist=False)
        self._update_nav_buttons()

    def _update_nav_buttons(self):
        self.btn_back.configure(state='normal' if self._history else 'disabled')
        self.btn_fwd.configure(state='normal' if self._fwd_hist else 'disabled')

    # ── Page navigation ──

    def _show_page(self, idx):
        if not self._pages: return
        idx = max(0, min(idx, len(self._pages)-1))
        self._page_idx = idx
        single_page = [(self._pages[idx][0], idx)]
        self.html_view.render(single_page)
        total = len(self._pages)
        self.lbl_page.configure(text=f'Page {idx+1} / {total}')
        self.btn_prev_page.configure(state='normal' if idx>0 else 'disabled')
        self.btn_next_page.configure(state='normal' if idx<total-1 else 'disabled')

    def _prev_page(self):
        if self._page_idx > 0:
            self._push_history()
            self._show_page(self._page_idx - 1)

    def _next_page(self):
        if self._page_idx < len(self._pages)-1:
            self._push_history()
            self._show_page(self._page_idx + 1)

    # ── Document loading ──

    def _open(self):
        paths = filedialog.askopenfilenames(
            title='Open iSilo .pdb file',
            filetypes=[('iSilo Documents','*.pdb *.PDB'),('All files','*.*')])
        for p in paths:
            if any(d.path==p for d in self.docs): continue
            try:
                doc = PdbDoc(p)
                self.docs.append(doc)
                self.lb.insert('end', doc.name or Path(p).name)
                self._set_status(f'Loaded: {Path(p).name} ({doc.format})')
            except Exception as e:
                messagebox.showerror('Error', f'Cannot open {Path(p).name}:\n{e}')
        if self.docs and not self.current:
            self.lb.selection_set(0); self._load_doc(self.docs[0])

    def _open_file(self, path, page_idx=0, scroll=None, push_hist=True):
        """Open a specific file path (for cross-doc links)."""
        # Check if already in library
        existing = next((d for d in self.docs if d.path==path), None)
        if not existing:
            try:
                existing = PdbDoc(path)
                self.docs.append(existing)
                self.lb.insert('end', existing.name or Path(path).name)
            except Exception as e:
                messagebox.showerror('Error', f'Cannot open {Path(path).name}:\n{e}')
                return
        if push_hist: self._push_history()
        self._load_doc(existing, page_idx=page_idx)
        if scroll is not None:
            self.root.after(50, lambda: self.html_view.yview_moveto(scroll))

    def _on_select(self, _=None):
        sel = self.lb.curselection()
        if sel: self._load_doc(self.docs[sel[0]])

    def _load_doc(self, doc, page_idx=0):
        self.current = doc
        self._set_status(f'Loading: {Path(doc.path).name}...')
        self.root.update()
        try:
            self._pages = doc.extract_html()
        except Exception as e:
            self._pages = [(f'<pre>Error: {e}</pre>', 0)]

        sz = os.path.getsize(doc.path)
        sz_l = f'{sz/1024:.1f} KB' if sz<1024*1024 else f'{sz/1024/1024:.2f} MB'
        self.lbl_info.configure(
            text=f'{doc.name}  |  {doc.format}  |  {doc.nrec} records  |  {sz_l}')

        total = len(self._pages)
        self.btn_prev_page.configure(state='disabled')
        self.btn_next_page.configure(state='normal' if total>1 else 'disabled')

        # Render - for small docs show all pages merged; for large show paginated
        if total <= 5:
            # Merge all pages into one view
            self.html_view.render(self._pages)
            self.lbl_page.configure(text=f'{total} page{"s" if total>1 else ""}')
            self.btn_prev_page.configure(state='disabled')
            self.btn_next_page.configure(state='disabled')
            self._page_idx = 0
        else:
            self._show_page(page_idx)

        self._set_status(f'Loaded: {Path(doc.path).name} — {total} page(s)')
        self._update_nav_buttons()

    def _remove(self):
        sel = self.lb.curselection()
        if not sel: return
        i = sel[0]; self.lb.delete(i); self.docs.pop(i)
        self.html_view.render([])
        self.lbl_info.configure(text='Open a .pdb file to begin')
        self.current = None

    def _resize(self, delta):
        self._fs = max(8, min(28, self._fs+delta))
        self.html_view.set_font_size(self._fs)
        if self.current:
            self._load_doc(self.current, self._page_idx)

    def _toggle_dark(self):
        self._dark = not self._dark
        self.btn_dark.configure(text='☀' if self._dark else '🌙')
        # Rebuild html widget
        parent = self.html_view.master
        old_sb = None
        for w in parent.winfo_children():
            if isinstance(w, ttk.Scrollbar): old_sb = w
        self.html_view.destroy()
        if old_sb: old_sb.destroy()

        vscroll = ttk.Scrollbar(parent, orient='vertical')
        self.html_view = HtmlTextWidget(
            parent, on_link=self._handle_link, dark=self._dark,
            font=('Segoe UI', self._fs), yscrollcommand=vscroll.set)
        vscroll.configure(command=self.html_view.yview)
        vscroll.pack(side='right', fill='y')
        self.html_view.pack(fill='both', expand=True)

        parent.configure(bg='#1E1E2E' if self._dark else 'white')
        if self.current:
            self._load_doc(self.current, self._page_idx)

    def _copy(self):
        if not self.current: return
        self.root.clipboard_clear()
        self.root.clipboard_append(self.html_view.get('1.0','end'))
        self._set_status('Copied to clipboard')

    def _save(self):
        if not self.current: return
        out = filedialog.asksaveasfilename(
            defaultextension='.txt',
            initialfile=Path(self.current.path).stem+'.txt',
            filetypes=[('Text','*.txt'),('All','*.*')])
        if not out: return
        content = self.html_view.get('1.0','end')
        open(out,'w',encoding='utf-8').write(content)
        self._set_status(f'Saved: {Path(out).name}')

    def _about(self):
        messagebox.showinfo(f'About {self.APP_NAME}',
            f'{self.APP_NAME} v{self.VERSION}\n\n'
            'Read iSilo .pdb documents on modern Windows.\n'
            'Free — no subscription required.\n\n'
            f'Developer: {self.AUTHOR}\n\n'
            'Supported formats:\n'
            '  iSilo 3.x, 4-6.x SilX (HTML + hyperlinks)\n'
            '  iSilo SDoc (metadata + index)\n'
            '  PalmDOC (plain text)\n\n'
            'Hyperlink types:\n'
            '  #anchor — internal document navigation\n'
            '  http/https — opens web browser\n'
            '  mailto: — opens mail app\n'
            '  tel: — shows phone number\n'
            '  file.pdb — opens linked document\n\n'
            'iSilo is a trademark of DC & Co.')

    def _set_status(self, msg):
        self.status.configure(text=f'  {msg}')


# ─────────────────────────── ENTRY POINT ───────────────────────────

def main():
    root = tk.Tk()
    root.minsize(750, 500)
    try: root.iconbitmap(default='isilo_recovery.ico')
    except: pass
    app = IsiloRecoveryApp(root)
    for p in sys.argv[1:]:
        if p.lower().endswith('.pdb') and os.path.exists(p):
            try:
                doc = PdbDoc(p)
                app.docs.append(doc)
                app.lb.insert('end', doc.name or Path(p).name)
                app._load_doc(doc)
            except Exception as e:
                print(f'Error: {e}')
    root.mainloop()

if __name__ == '__main__':
    main()
