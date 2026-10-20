#!/usr/bin/env python3
"""
iSilo Recovery - Windows PDB Reader
Developer: seriusman0@gmail.com
Read iSilo .pdb documents on Windows without subscription.

Requires: Python 3.8+ with tkinter (bundled with Python on Windows)
Run: python isilo_recovery.py
"""
import sys, struct, zlib, os, binascii
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, font
from typing import Optional

# ---- PDB Parser ----

def u16(d, o): return struct.unpack('>H', d[o:o+2])[0]
def u32(d, o): return struct.unpack('>I', d[o:o+4])[0]

class PdbDoc:
    def __init__(self, path):
        self.path = path
        self.data = open(path, 'rb').read()
        self._parse()

    def _parse(self):
        d = self.data
        if len(d) < 78:
            raise ValueError(f"File too small ({len(d)} bytes)")
        nb = d[0:32]
        ne = nb.find(0)
        self.name = nb[:ne if ne>=0 else 32].decode('latin-1')
        self.db_type   = d[60:64].decode('latin-1')
        self.creator   = d[64:68].decode('latin-1')
        self.nrec = u16(d, 76)
        # Palm epoch: Jan 1, 1904
        cdate = u32(d, 36)
        try:
            import datetime
            self.created = datetime.datetime(1904,1,1) + datetime.timedelta(seconds=cdate)
        except:
            self.created = None

        offs = []
        for i in range(self.nrec):
            o = 78 + i*8
            if o+8 > len(d): break
            offs.append((u32(d, o), d[o+4]))
        self.records = []
        for i,(off,attr) in enumerate(offs):
            end = offs[i+1][0] if i+1 < len(offs) else len(d)
            self.records.append(d[off:end])

        if self.creator == 'iSil' and self.db_type == 'SilX':
            self.format = 'iSilo 4-6.x (SilX)'
        elif self.creator == 'iSil' and self.db_type == 'iSil':
            self.format = 'iSilo 3.x'
        elif self.creator == 'REAd' and self.db_type == 'TEXt':
            self.format = 'PalmDOC'
        else:
            self.format = f'Palm DB ({self.db_type}/{self.creator})'

    def extract_text(self):
        """Extract readable content from PDB records"""
        if 'PalmDOC' in self.format:
            return self._palmDoc()
        return self._iSilo()

    def _palmDoc(self):
        if not self.records: return ''
        r0 = self.records[0]
        compression = u16(r0, 0) if len(r0)>=2 else 1
        buf = []
        for rec in self.records[1:]:
            if compression == 2:
                buf.append(self._palmDocLZ(rec).decode('latin-1', errors='replace'))
            else:
                buf.append(rec.decode('latin-1', errors='replace'))
        return ''.join(buf)

    def _palmDocLZ(self, data):
        out = []
        i = 0
        while i < len(data):
            c = data[i]; i+=1
            if c==0: out.append(0)
            elif c<=8:
                for _ in range(c):
                    if i<len(data): out.append(data[i]); i+=1
            elif c<=0x7F: out.append(c)
            elif c<=0xBF:
                if i>=len(data): break
                n=data[i]; i+=1
                dist=(c&0x3F)<<8|n; length=(dist&7)+3; offset=(dist>>3)&0x1FFF
                start=len(out)-offset
                for j in range(length):
                    out.append(out[start+j] if 0<=start+j<len(out) else 0x20)
            else:
                out.append(0x20); out.append(c^0x80)
        return bytes(out)

    def _iSilo(self):
        buf = []
        for i, rec in enumerate(self.records[1:], 1):
            if not rec: continue
            # Try zlib with various offsets
            text = None
            for start in range(0, min(len(rec), 12)):
                try:
                    dec = zlib.decompress(rec[start:])
                    if dec:
                        text = dec.decode('utf-8', errors='replace')
                        break
                except:
                    pass
            if text and self._looks_like_text(text):
                buf.append(text)
            elif self._looks_like_text_bytes(rec):
                buf.append(rec.decode('utf-8', errors='replace'))
        result = ''.join(buf).strip()
        if not result:
            # Fallback: extract all printable ASCII
            result = ''.join(chr(b) if 32<=b<127 or b in (9,10,13) else ' ' for b in self.data)
        return result

    def _looks_like_text(self, s):
        if not s: return False
        sample = s[:200]
        p = sum(1 for c in sample if c.isprintable() or c in '\t\n\r')
        return p > len(sample)*0.6

    def _looks_like_text_bytes(self, d):
        if not d: return False
        sample = d[:200]
        p = sum(1 for b in sample if 32<=b<127 or b in (9,10,13))
        return p > len(sample)*0.7


# ---- GUI ----

class IsiloRecoveryApp:
    APP_NAME = "iSilo Recovery"
    VERSION  = "1.0.0"
    AUTHOR   = "seriusman0@gmail.com"
    BG       = "#1A237E"
    FG       = "#FFFFFF"
    CARD_BG  = "#F5F5F5"

    def __init__(self, root):
        self.root = root
        self.root.title(self.APP_NAME)
        self.root.geometry("1000x680")
        self.root.configure(bg=self.BG)
        self.docs = []     # list of PdbDoc
        self.current = None
        self._build_ui()

    def _build_ui(self):
        # Top bar
        bar = tk.Frame(self.root, bg=self.BG, pady=8)
        bar.pack(fill='x')
        tk.Label(bar, text=f"\U0001F4D6  {self.APP_NAME}", bg=self.BG, fg=self.FG,
                 font=('Segoe UI', 16, 'bold')).pack(side='left', padx=16)
        tk.Label(bar, text="Read iSilo .pdb files — free, no subscription",
                 bg=self.BG, fg='#90CAF9', font=('Segoe UI', 10)).pack(side='left')
        tk.Button(bar, text="Open .pdb file(s)", command=self._open,
                  bg="#283593", fg=self.FG, relief='flat', padx=12, pady=4,
                  font=('Segoe UI', 10, 'bold'), cursor='hand2').pack(side='right', padx=16)
        tk.Button(bar, text="About", command=self._about,
                  bg=self.BG, fg='#90CAF9', relief='flat', padx=8,
                  font=('Segoe UI', 9), cursor='hand2').pack(side='right')

        # Main pane
        pane = tk.PanedWindow(self.root, orient='horizontal', bg='#E0E0E0', sashwidth=4)
        pane.pack(fill='both', expand=True, padx=0, pady=0)

        # Left: library list
        left = tk.Frame(pane, bg='#E8EAF6', width=240)
        pane.add(left, minsize=180)

        tk.Label(left, text="Library", bg='#E8EAF6', fg='#283593',
                 font=('Segoe UI', 11, 'bold')).pack(pady=(10,4), padx=10, anchor='w')

        self.listbox = tk.Listbox(left, bg='white', fg='#1A237E',
                                  selectbackground='#1A237E', selectforeground='white',
                                  font=('Segoe UI', 10), relief='flat',
                                  activestyle='none', borderwidth=0)
        self.listbox.pack(fill='both', expand=True, padx=6, pady=(0,6))
        self.listbox.bind('<<ListboxSelect>>', self._on_select)

        sbL = ttk.Scrollbar(left, orient='vertical', command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sbL.set)
        sbL.pack(side='right', fill='y')

        btn_frame = tk.Frame(left, bg='#E8EAF6')
        btn_frame.pack(fill='x', padx=6, pady=4)
        tk.Button(btn_frame, text="Remove", command=self._remove,
                  bg='#EF9A9A', fg='#B71C1C', relief='flat', font=('Segoe UI', 9),
                  cursor='hand2', pady=2).pack(side='left', padx=(0,4))

        # Right: reader
        right = tk.Frame(pane, bg='white')
        pane.add(right, minsize=400)

        # Toolbar
        tbar = tk.Frame(right, bg='#ECEFF1', pady=4)
        tbar.pack(fill='x')
        self.lbl_info = tk.Label(tbar, text="Open a .pdb file to begin",
                                 bg='#ECEFF1', fg='#546E7A', font=('Segoe UI', 9))
        self.lbl_info.pack(side='left', padx=10)
        tk.Button(tbar, text="−A", command=lambda: self._font_size(-1),
                  relief='flat', bg='#ECEFF1', font=('Segoe UI', 9), cursor='hand2').pack(side='right', padx=2)
        tk.Button(tbar, text="+A", command=lambda: self._font_size(1),
                  relief='flat', bg='#ECEFF1', font=('Segoe UI', 9), cursor='hand2').pack(side='right', padx=2)
        tk.Button(tbar, text="Copy all", command=self._copy,
                  relief='flat', bg='#ECEFF1', font=('Segoe UI', 9), cursor='hand2').pack(side='right', padx=4)
        tk.Button(tbar, text="Save as .txt", command=self._save_txt,
                  relief='flat', bg='#283593', fg='white', font=('Segoe UI', 9), cursor='hand2',
                  padx=6).pack(side='right', padx=4)

        # Text area
        txt_frame = tk.Frame(right, bg='white')
        txt_frame.pack(fill='both', expand=True)
        self._font_pt = 13
        self._font_obj = font.Font(family='Segoe UI', size=self._font_pt)
        self.text = tk.Text(txt_frame, font=self._font_obj, wrap='word',
                            bg='#FAFAFA', fg='#1A1A2E', relief='flat',
                            padx=20, pady=16, state='disabled',
                            spacing1=2, spacing2=4)
        sb = ttk.Scrollbar(txt_frame, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side='right', fill='y')
        self.text.pack(fill='both', expand=True)

        # Status bar
        self.status = tk.Label(self.root, text="Ready", bg='#283593', fg='white',
                               font=('Segoe UI', 9), anchor='w', pady=3)
        self.status.pack(fill='x', side='bottom')

    def _set_status(self, msg):
        self.status.config(text=f"  {msg}")

    def _open(self):
        paths = filedialog.askopenfilenames(
            title="Open iSilo .pdb file",
            filetypes=[("iSilo Documents", "*.pdb *.PDB"), ("All files", "*.*")]
        )
        for p in paths:
            if any(d.path==p for d in self.docs):
                continue
            try:
                doc = PdbDoc(p)
                self.docs.append(doc)
                self.listbox.insert('end', doc.name or Path(p).name)
                self._set_status(f"Loaded: {Path(p).name} ({doc.format})")
            except Exception as e:
                messagebox.showerror("Error", f"Cannot open {Path(p).name}:\n{e}")
        if self.docs and not self.current:
            self.listbox.selection_set(0)
            self._load_doc(self.docs[0])

    def _on_select(self, _=None):
        sel = self.listbox.curselection()
        if sel:
            self._load_doc(self.docs[sel[0]])

    def _load_doc(self, doc):
        self.current = doc
        self._set_status(f"Extracting: {Path(doc.path).name}...")
        self.root.update()
        try:
            text = doc.extract_text()
        except Exception as e:
            text = f"[Error extracting text: {e}]"
        sz = os.path.getsize(doc.path)
        sz_label = f"{sz:,} bytes" if sz < 1024*1024 else f"{sz/1024/1024:.2f} MB"
        info = (f"Title: {doc.name}  |  Format: {doc.format}  |  "
                f"Records: {doc.nrec}  |  Size: {sz_label}")
        self.lbl_info.config(text=info)
        self.text.config(state='normal')
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', text if text.strip() else "[No readable text found in this document]")
        self.text.config(state='disabled')
        self._set_status(f"Loaded: {Path(doc.path).name} — {len(text)} chars extracted")

    def _remove(self):
        sel = self.listbox.curselection()
        if not sel: return
        i = sel[0]
        self.listbox.delete(i)
        self.docs.pop(i)
        self.text.config(state='normal')
        self.text.delete('1.0','end')
        self.text.config(state='disabled')
        self.lbl_info.config(text="Open a .pdb file to begin")
        self.current = None

    def _font_size(self, delta):
        self._font_pt = max(8, min(28, self._font_pt + delta))
        self._font_obj.configure(size=self._font_pt)

    def _copy(self):
        if not self.current: return
        content = self.text.get('1.0','end')
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self._set_status("Text copied to clipboard")

    def _save_txt(self):
        if not self.current: return
        out = filedialog.asksaveasfilename(
            defaultextension='.txt',
            initialfile=Path(self.current.path).stem + '.txt',
            filetypes=[("Text file","*.txt"),("All","*.*")]
        )
        if not out: return
        content = self.text.get('1.0','end')
        open(out,'w',encoding='utf-8').write(content)
        self._set_status(f"Saved: {Path(out).name}")

    def _about(self):
        messagebox.showinfo(
            f"About {self.APP_NAME}",
            f"{self.APP_NAME} v{self.VERSION}\n\n"
            "Read your classic iSilo .pdb documents\n"
            "on modern Windows — free, no subscription.\n\n"
            f"Developer: {self.AUTHOR}\n\n"
            "Supports:\n"
            "  • iSilo 3.x, 4.x, 5.x, 6.x (SilX)\n"
            "  • PalmDOC format\n\n"
            "iSilo is a trademark of DC & Co."
        )


def main():
    root = tk.Tk()
    root.minsize(700, 450)
    # icon (optional)
    try:
        root.iconbitmap(default='isilo_recovery.ico')
    except:
        pass
    app = IsiloRecoveryApp(root)
    # Accept file argument from command line or drag-and-drop
    if len(sys.argv) > 1:
        for p in sys.argv[1:]:
            if p.lower().endswith('.pdb') and os.path.exists(p):
                try:
                    doc = PdbDoc(p)
                    app.docs.append(doc)
                    app.listbox.insert('end', doc.name or Path(p).name)
                    app._load_doc(doc)
                except Exception as e:
                    print(f"Error: {e}")
    root.mainloop()

if __name__ == '__main__':
    main()
