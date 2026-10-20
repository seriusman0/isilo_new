#!/usr/bin/env python3
"""
iSilo Recovery - Windows PDB Reader v1.1
Developer: seriusman0@gmail.com
Read iSilo .pdb documents on modern Windows - free, no subscription.

Supported formats:
  - iSilo 3.x (type: iSil / creator: iSil)
  - iSilo 4-6.x SilX (type: SilX / creator: iSil) - with zlib decompression
  - iSilo SDoc (type: SDoc / creator: SilX) - metadata + index extraction  
  - PalmDOC (type: TEXt / creator: REAd) - full text

Run: python isilo_recovery.py [file.pdb ...]
"""
import sys, struct, zlib, os, re
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
        self.name = nb[:ne if ne>=0 else 32].decode('latin-1', errors='replace').strip()
        self.db_type  = d[60:64].decode('latin-1', errors='replace')
        self.creator  = d[64:68].decode('latin-1', errors='replace')
        self.nrec = u16(d, 76)
        try:
            import datetime
            cdate = u32(d, 36)
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
            seg = d[off:end]
            self.records.append(seg)

        if self.creator == 'iSil' and self.db_type == 'SilX':
            self.format = 'iSilo 4-6.x (SilX)'
        elif self.creator == 'iSil' and self.db_type == 'iSil':
            self.format = 'iSilo 3.x'
        elif self.creator == 'REAd' and self.db_type == 'TEXt':
            self.format = 'PalmDOC'
        elif self.creator == 'SilX' and self.db_type == 'SDoc':
            self.format = 'iSilo SDoc (SilX)'
        else:
            self.format = f'Palm DB ({self.db_type}/{self.creator})'

    def extract_text(self):
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
                for j in range(length): out.append(out[start+j] if 0<=start+j<len(out) else 0x20)
            else:
                out.append(0x20); out.append(c^0x80)
        return bytes(out)

    def _iSilo(self):
        buf = []
        # Try zlib decompression on each record
        for rec in self.records[1:]:
            if not rec: continue
            for start in range(0, min(len(rec), 12)):
                try:
                    dec = zlib.decompress(rec[start:])
                    if len(dec) > 20:
                        t = dec.decode('utf-8', errors='replace')
                        if self._looks_text(t):
                            buf.append(t); break
                except: pass
            else:
                if self._looks_text_bytes(rec):
                    buf.append(rec.decode('utf-8', errors='replace'))
        
        result = ''.join(buf).strip()
        
        # For SDoc format: also extract TOC/index (always readable)
        toc = self._extract_toc()
        
        if not result and not toc:
            return self._metadata_summary()
        
        if toc:
            if result:
                return result + "\n\n--- Document Index ---\n" + toc
            else:
                return self._metadata_summary() + "\n\n--- Document Index (partial text) ---\n" + toc
        
        return result

    def _extract_toc(self):
        """Extract readable text from TOC/index (last records)."""
        buf = []
        for rec in self.records[-5:]:
            entries = rec.split(b'\x00')
            for e in entries:
                if len(e) < 4: continue
                clean = e.replace(b'\xa0', b' ').decode('latin-1', errors='replace')
                clean = re.sub(r'[^\x20-\x7e\n\t]', '', clean).strip()
                if len(clean) > 8:
                    buf.append(clean)
        return '\n'.join(buf)

    def _metadata_summary(self):
        sz = os.path.getsize(self.path)
        lines = [
            f"Document: {self.name}",
            f"Format: {self.format}",
            f"Type/Creator: {self.db_type} / {self.creator}",
            f"Records: {self.nrec}",
            f"File size: {sz:,} bytes ({sz/1024:.1f} KB)",
        ]
        if self.created:
            lines.append(f"Created: {self.created.strftime('%Y-%m-%d')}")
        lines.append("")
        lines.append("Note: This document uses iSilo proprietary SDoc compression.")
        lines.append("Full text extraction requires the iSilo native decompressor.")
        lines.append("Showing available metadata and index entries below.")
        return '\n'.join(lines)

    def _looks_text(self, s):
        if not s: return False
        sample = s[:300]
        p = sum(1 for c in sample if c.isprintable() or c in '\t\n\r')
        return p > len(sample)*0.6

    def _looks_text_bytes(self, d):
        if not d: return False
        sample = d[:200]
        p = sum(1 for b in sample if 32<=b<127 or b in (9,10,13))
        return p > len(sample)*0.7


# ---- GUI ----
class IsiloRecoveryApp:
    APP_NAME = "iSilo Recovery"
    VERSION  = "1.1.0"
    AUTHOR   = "seriusman0@gmail.com"
    BG       = "#1A237E"
    FG       = "#FFFFFF"

    def __init__(self, root):
        self.root = root
        self.root.title(self.APP_NAME)
        self.root.geometry("1000x680")
        self.root.configure(bg=self.BG)
        self.docs = []
        self.current = None
        self._build_ui()

    def _build_ui(self):
        # Top bar
        bar = tk.Frame(self.root, bg=self.BG, pady=8)
        bar.pack(fill='x')
        tk.Label(bar, text=f"\U0001F4D6  {self.APP_NAME}",
                 bg=self.BG, fg=self.FG,
                 font=('Segoe UI', 16, 'bold')).pack(side='left', padx=16)
        tk.Label(bar, text="Read iSilo .pdb files  free, no subscription",
                 bg=self.BG, fg='#90CAF9', font=('Segoe UI', 10)).pack(side='left')
        tk.Button(bar, text="Open .pdb file(s)", command=self._open,
                  bg="#283593", fg=self.FG, relief='flat', padx=12, pady=4,
                  font=('Segoe UI', 10, 'bold'), cursor='hand2').pack(side='right', padx=16)
        tk.Button(bar, text="About", command=self._about,
                  bg=self.BG, fg='#90CAF9', relief='flat', padx=8,
                  font=('Segoe UI', 9), cursor='hand2').pack(side='right')

        # Main pane
        pane = tk.PanedWindow(self.root, orient='horizontal', bg='#E0E0E0', sashwidth=4)
        pane.pack(fill='both', expand=True)

        # Left: library
        left = tk.Frame(pane, bg='#E8EAF6', width=240)
        pane.add(left, minsize=180)
        tk.Label(left, text="Library", bg='#E8EAF6', fg='#283593',
                 font=('Segoe UI', 11, 'bold')).pack(pady=(10,4), padx=10, anchor='w')
        self.listbox = tk.Listbox(left, bg='white', fg='#1A237E',
                                   selectbackground='#1A237E', selectforeground='white',
                                   font=('Segoe UI', 10), relief='flat', activestyle='none', borderwidth=0)
        self.listbox.pack(fill='both', expand=True, padx=6, pady=(0,6))
        self.listbox.bind('<<ListboxSelect>>', self._on_select)
        sbL = ttk.Scrollbar(left, orient='vertical', command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sbL.set)
        sbL.pack(side='right', fill='y')
        btn_frame = tk.Frame(left, bg='#E8EAF6')
        btn_frame.pack(fill='x', padx=6, pady=4)
        tk.Button(btn_frame, text="Remove", command=self._remove,
                  bg='#EF9A9A', fg='#B71C1C', relief='flat', font=('Segoe UI', 9),
                  cursor='hand2', pady=2).pack(side='left')

        # Right: reader
        right = tk.Frame(pane, bg='white')
        pane.add(right, minsize=400)

        # Toolbar
        tbar = tk.Frame(right, bg='#ECEFF1', pady=4)
        tbar.pack(fill='x')
        self.lbl_info = tk.Label(tbar, text="Open a .pdb file to begin",
                                  bg='#ECEFF1', fg='#546E7A', font=('Segoe UI', 9))
        self.lbl_info.pack(side='left', padx=10)
        tk.Button(tbar, text="-A", command=lambda: self._fs(-1),
                  relief='flat', bg='#ECEFF1', cursor='hand2').pack(side='right', padx=2)
        tk.Button(tbar, text="+A", command=lambda: self._fs(1),
                  relief='flat', bg='#ECEFF1', cursor='hand2').pack(side='right', padx=2)
        tk.Button(tbar, text="Copy all", command=self._copy,
                  relief='flat', bg='#ECEFF1', font=('Segoe UI', 9), cursor='hand2').pack(side='right', padx=4)
        tk.Button(tbar, text="Save as .txt", command=self._save,
                  relief='flat', bg='#283593', fg='white', font=('Segoe UI', 9),
                  cursor='hand2', padx=6).pack(side='right', padx=4)

        # Text area
        txt_frame = tk.Frame(right, bg='white')
        txt_frame.pack(fill='both', expand=True)
        self._fp = 13
        self._fo = font.Font(family='Segoe UI', size=self._fp)
        self.text = tk.Text(txt_frame, font=self._fo, wrap='word',
                             bg='#FAFAFA', fg='#1A1A2E', relief='flat',
                             padx=20, pady=16, state='disabled', spacing1=2, spacing2=4)
        sb2 = ttk.Scrollbar(txt_frame, command=self.text.yview)
        self.text.configure(yscrollcommand=sb2.set)
        sb2.pack(side='right', fill='y')
        self.text.pack(fill='both', expand=True)

        # Status
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
            if any(d.path==p for d in self.docs): continue
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
        if sel: self._load_doc(self.docs[sel[0]])

    def _load_doc(self, doc):
        self.current = doc
        self._set_status(f"Extracting: {Path(doc.path).name}...")
        self.root.update()
        try:
            text = doc.extract_text()
        except Exception as e:
            text = f"[Error: {e}]"
        sz = os.path.getsize(doc.path)
        sz_l = f"{sz/1024:.1f} KB" if sz < 1024*1024 else f"{sz/1024/1024:.2f} MB"
        self.lbl_info.config(text=f"{doc.name}  |  {doc.format}  |  {doc.nrec} records  |  {sz_l}")
        self.text.config(state='normal')
        self.text.delete('1.0', 'end')
        self.text.insert('1.0', text if text.strip() else "[No readable text found]")
        self.text.config(state='disabled')
        self._set_status(f"Loaded: {Path(doc.path).name} - {len(text):,} chars")

    def _remove(self):
        sel = self.listbox.curselection()
        if not sel: return
        i = sel[0]
        self.listbox.delete(i); self.docs.pop(i)
        self.text.config(state='normal'); self.text.delete('1.0','end'); self.text.config(state='disabled')
        self.lbl_info.config(text="Open a .pdb file to begin"); self.current = None

    def _fs(self, d):
        self._fp = max(8, min(28, self._fp+d)); self._fo.configure(size=self._fp)

    def _copy(self):
        if not self.current: return
        self.root.clipboard_clear(); self.root.clipboard_append(self.text.get('1.0','end'))
        self._set_status("Copied to clipboard")

    def _save(self):
        if not self.current: return
        out = filedialog.asksaveasfilename(
            defaultextension='.txt', initialfile=Path(self.current.path).stem+'.txt',
            filetypes=[("Text","*.txt"),("All","*.*")])
        if not out: return
        open(out,'w',encoding='utf-8').write(self.text.get('1.0','end'))
        self._set_status(f"Saved: {Path(out).name}")

    def _about(self):
        messagebox.showinfo(f"About {self.APP_NAME}",
            f"{self.APP_NAME} v{self.VERSION}\n\n"
            "Read iSilo .pdb documents on modern Windows\n"
            "Free - no subscription required.\n\n"
            f"Developer: {self.AUTHOR}\n\n"
            "Supported formats:\n"
            "  iSilo 3.x, 4-6.x (SilX), PalmDOC\n"
            "  iSilo SDoc (metadata + index)\n\n"
            "iSilo is a trademark of DC & Co.")


def main():
    root = tk.Tk()
    root.minsize(700, 450)
    try: root.iconbitmap(default='isilo_recovery.ico')
    except: pass
    app = IsiloRecoveryApp(root)
    for p in sys.argv[1:]:
        if p.lower().endswith('.pdb') and os.path.exists(p):
            try:
                doc = PdbDoc(p)
                app.docs.append(doc)
                app.listbox.insert('end', doc.name or Path(p).name)
                app._load_doc(doc)
            except Exception as e:
                print(f"Error opening {p}: {e}")
    root.mainloop()

if __name__ == '__main__':
    main()
