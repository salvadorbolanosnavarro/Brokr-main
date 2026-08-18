from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

assignment = '_thread_pool = concurrent.futures.ThreadPoolExecutor(max_workers=4)\n'
import_line = 'from core.executors import _thread_pool\n'

if import_line not in source:
    anchor = 'from core.pdf_store import _pdf_store\n'
    if source.count(anchor) != 1:
        raise SystemExit("unexpected shared executor import anchor")
    source = source.replace(anchor, anchor + import_line, 1)

if assignment in source:
    if source.count(assignment) != 1:
        raise SystemExit("unexpected shared executor assignment count")
    source = source.replace(assignment, '', 1)

if assignment in source:
    raise SystemExit("legacy thread pool assignment remains in main")
if source.count(import_line) != 1:
    raise SystemExit("shared executor import not present exactly once")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
