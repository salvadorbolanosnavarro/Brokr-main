from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

start_marker = 'async def fetch_all_properties() -> list:\n'
end_marker = '# ────────────────────────────────────────────\n# AVM — HELPERS\n'
if start_marker in source:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    block = source[start:end]
    if '@app.' in block:
        raise SystemExit("unexpected route inside dead EasyBroker helper block")
    source = source[:start] + end_marker + source[end + len(end_marker):]
elif 'fetch_all_properties(' in source:
    raise SystemExit("unexpected fetch_all_properties state")

if 'fetch_all_properties(' in source:
    raise SystemExit("dead fetch_all_properties remains in main")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
