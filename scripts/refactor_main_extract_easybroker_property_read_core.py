from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Diagnóstico de la API de EasyBroker (solo lectura).\nfrom routers.easybroker_diagnostics import router as easybroker_diagnostics_router\napp.include_router(easybroker_diagnostics_router)\n'''
mount_block = mount_anchor + '''\n# Lectura autenticada de propiedades EasyBroker.\nfrom routers.easybroker_properties import router as easybroker_properties_router\napp.include_router(easybroker_properties_router)\n'''
if source.count('from routers.easybroker_properties import router as easybroker_properties_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected EasyBroker property mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.easybroker_properties import router as easybroker_properties_router') != 1:
    raise SystemExit("unexpected EasyBroker property mount state")

route_start = '@app.get("/propiedad/{property_id}")'
next_marker = '''# ════════════════════════════════════════════════════════════════\n# IMPORTACIÓN MASIVA DESDE EASYBROKER\n'''
if route_start in source:
    start = source.index(route_start)
    end = source.index(next_marker, start)
    source = source[:start] + source[end:]
elif 'async def get_propiedad(' in source:
    raise SystemExit("unexpected partially extracted EasyBroker property route")

for legacy in ('@app.get("/propiedad/{property_id}")', 'async def get_propiedad('):
    if legacy in source:
        raise SystemExit(f"EasyBroker property read symbol remains in main: {legacy}")
if source.count('app.include_router(easybroker_properties_router)') != 1:
    raise SystemExit("EasyBroker property router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
