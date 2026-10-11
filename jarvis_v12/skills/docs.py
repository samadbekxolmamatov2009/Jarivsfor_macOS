"""Reads documents aloud or summarizes them: the file selected in Finder, a named file, or your newest download."""
import glob
import os
import re
import subprocess
import time

EXTS = (".pdf", ".docx", ".txt", ".md", ".rtf")
FINDER = 'tell application "Finder" to get POSIX path of (item 1 of (get selection) as alias)'


def selected_file():
    """(path, problem). problem: None, 'permission', 'not a document' or 'nothing selected'."""
    try:
        r = subprocess.run(["osascript", "-e", FINDER], capture_output=True, text=True, timeout=5)
    except Exception:
        return None, "nothing selected"
    if "1743" in r.stderr or "not allowed" in r.stderr.lower():
        return None, "permission"
    p = r.stdout.strip()
    if not p:
        return None, "nothing selected"
    if not os.path.isfile(p) or not p.lower().endswith(EXTS):
        return None, "not a document"
    return p, None


def newest_document(days=7):
    files = []
    for d in ("~/Downloads", "~/Desktop", "~/Documents"):
        for ext in EXTS:
            files += glob.glob(os.path.join(os.path.expanduser(d), "*" + ext))
    files = [f for f in files if time.time() - os.path.getmtime(f) < days * 86400]
    return max(files, key=os.path.getmtime) if files else None


def read_text(path, limit=60000):
    low = path.lower()
    if low.endswith(".pdf"):
        from pypdf import PdfReader
        text = "\n".join((pg.extract_text() or "") for pg in PdfReader(path).pages[:60])
    elif low.endswith(".docx"):
        from docx import Document
        d = Document(path)
        parts = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                parts.append(" | ".join(c.text for c in row.cells))
        text = "\n".join(parts)
    elif low.endswith(".rtf"):
        text = subprocess.run(["textutil", "-convert", "txt", "-stdout", path], capture_output=True, text=True).stdout
    else:
        text = open(path, encoding="utf-8", errors="ignore").read()
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()[:limit]


def sentences(text):
    """Splits text into speakable pieces."""
    for block in re.split(r"\n+", text):
        block = block.strip()
        if not block:
            continue
        for s in re.split(r"(?<=[.!?])\s+", block):
            if s.strip():
                yield s.strip()
