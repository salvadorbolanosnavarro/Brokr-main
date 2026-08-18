from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Lectura autenticada de propiedades EasyBroker.\nfrom routers.easybroker_properties import router as easybroker_properties_router\napp.include_router(easybroker_properties_router)\n'''
mount_block = mount_anchor + '''\n# Listado legacy de propiedades EasyBroker (solo lectura).\nfrom routers.easybroker_catalog import router as easybroker_catalog_router\napp.include_router(easybroker_catalog_router)\n'''
if source.count('from routers.easybroker_catalog import router as easybroker_catalog_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected EasyBroker catalog mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.easybroker_catalog import router as easybroker_catalog_router') != 1:
    raise SystemExit("unexpected EasyBroker catalog mount state")

route_start = '@app.get("/propiedades")'
next_marker = '''# ────────────────────────────────────────────\n# COLONIAS AUTOCOMPLETE\n'''
if route_start in source:
    start = source.index(route_start)
    end = source.index(next_marker, start)
    source = source[:start] + source[end:]
elif 'async def get_propiedades(' in source:
    raise SystemExit("unexpected partially extracted EasyBroker catalog route")

for legacy in ('@app.get("/propiedades")', 'async def get_propiedades('):
    if legacy in source:
        raise SystemExit(f"EasyBroker catalog symbol remains in main: {legacy}")
if source.count('app.include_router(easybroker_catalog_router)') != 1:
    raise SystemExit("EasyBroker catalog router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
