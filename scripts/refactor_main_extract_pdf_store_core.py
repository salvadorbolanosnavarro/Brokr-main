from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

import_anchor = 'from core.pdf_design import theme_css_for_pdf\n'
import_line = 'from core.pdf_store import _pdf_store\n'
if import_line not in source:
    if source.count(import_anchor) != 1:
        raise SystemExit("unexpected PDF store import anchor")
    source = source.replace(import_anchor, import_anchor + import_line, 1)

legacy = '''# In-memory PDF store: token → (bytes, filename). Max 50 entradas.\n_pdf_store: dict = {}\n\n'''
if legacy in source:
    source = source.replace(legacy, "", 1)
elif '_pdf_store: dict = {}' in source:
    raise SystemExit("unexpected local PDF store shape")

if '_pdf_store: dict = {}' in source:
    raise SystemExit("local PDF store remains in main")
if source.count(import_line.strip()) != 1:
    raise SystemExit("Core PDF store not imported exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
