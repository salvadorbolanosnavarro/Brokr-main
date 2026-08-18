from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Listado legacy de propiedades EasyBroker (solo lectura).\nfrom routers.easybroker_catalog import router as easybroker_catalog_router\napp.include_router(easybroker_catalog_router)\n'''
mount_block = mount_anchor + '''\n# Autocomplete de colonias desde EasyBroker.\nfrom routers.easybroker_colonias import router as easybroker_colonias_router\napp.include_router(easybroker_colonias_router)\n'''
if source.count('from routers.easybroker_colonias import router as easybroker_colonias_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected EasyBroker colonias mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.easybroker_colonias import router as easybroker_colonias_router') != 1:
    raise SystemExit("unexpected EasyBroker colonias mount state")

old_import = 'from core.easybroker import EB_API_KEY, EB_BASE, _EB_LOTE, _EB_PAUSA_LOTE, _eb_get_reintentos, eb_headers\n'
new_import = 'from core.easybroker import EB_API_KEY, EB_BASE, _EB_LOTE, _EB_PAUSA_LOTE, _eb_get_reintentos, eb_headers, extract_colonia, normalize\n'
if old_import in source:
    source = source.replace(old_import, new_import, 1)
elif new_import not in source:
    raise SystemExit("unexpected core.easybroker import state")

extract_block = '''def extract_colonia(location_str: str) -> str:\n    """Extract colonia from 'Colonia, Ciudad, Estado' string."""\n    if not location_str:\n        return ""\n    parts = [p.strip() for p in location_str.split(",")]\n    return parts[0] if parts else location_str.strip()\n\n'''
if extract_block in source:
    source = source.replace(extract_block, "", 1)
elif 'def extract_colonia(' in source:
    raise SystemExit("unexpected extract_colonia shape")

normalize_block = '''def normalize(s: str) -> str:\n    for a, b in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ü','u'),('ñ','n')]:\n        s = s.lower().replace(a, b)\n    return s\n\n'''
if normalize_block in source:
    source = source.replace(normalize_block, "", 1)
elif 'def normalize(s: str)' in source:
    raise SystemExit("unexpected normalize shape")

route_start = '@app.get("/colonias")'
next_marker = '''# ────────────────────────────────────────────\n# AVM — HELPERS\n'''
if route_start in source:
    start = source.index(route_start)
    end = source.index(next_marker, start)
    source = source[:start] + source[end:]
elif 'async def get_colonias(' in source:
    raise SystemExit("unexpected partially extracted colonias route")

for legacy in ('@app.get("/colonias")', 'async def get_colonias(', 'def extract_colonia(', 'def normalize(s: str)'):
    if legacy in source:
        raise SystemExit(f"EasyBroker colonias symbol remains in main: {legacy}")
if source.count('app.include_router(easybroker_colonias_router)') != 1:
    raise SystemExit("EasyBroker colonias router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
