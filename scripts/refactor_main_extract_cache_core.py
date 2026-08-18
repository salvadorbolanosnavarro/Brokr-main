from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

import_anchor = '''from core.user_access import get_user_access_state, get_user_rol\n'''
import_line = '''from core.cache import cache_get, cache_set\n'''
if source.count(import_line) == 0:
    if source.count(import_anchor) != 1:
        raise SystemExit("unexpected cache import anchor")
    source = source.replace(import_anchor, import_anchor + import_line, 1)
elif source.count(import_line) != 1:
    raise SystemExit("unexpected cache import state")

cache_start = '''# ── CACHE EN MEMORIA (TTL 6h) ──\n'''
cache_end = '''def eb_headers(key: str = None):\n'''
if cache_start in source:
    start = source.index(cache_start)
    end = source.index(cache_end, start)
    source = source[:start] + source[end:]
elif 'def cache_get(' in source or 'def cache_set(' in source:
    raise SystemExit("unexpected partially extracted cache helpers")

for legacy in (
    'def cache_get(',
    'def cache_set(',
    '_cache_ttl: dict = {}',
    'CACHE_TTL = 21600',
):
    if legacy in source:
        raise SystemExit(f"cache symbol remains in main: {legacy}")
if source.count(import_line) != 1:
    raise SystemExit("Core cache import not present exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
