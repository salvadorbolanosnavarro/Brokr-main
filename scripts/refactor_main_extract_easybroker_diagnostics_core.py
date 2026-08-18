from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Conexión EasyBroker compartida por organización.\nfrom routers.easybroker_config import get_eb_key_for_user, router as easybroker_config_router\napp.include_router(easybroker_config_router)\n'''
mount_block = mount_anchor + '''\n# Diagnóstico de la API de EasyBroker (solo lectura).\nfrom routers.easybroker_diagnostics import router as easybroker_diagnostics_router\napp.include_router(easybroker_diagnostics_router)\n'''
if source.count('from routers.easybroker_diagnostics import router as easybroker_diagnostics_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected EasyBroker diagnostics mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.easybroker_diagnostics import router as easybroker_diagnostics_router') != 1:
    raise SystemExit("unexpected EasyBroker diagnostics mount state")

route_start = '@app.get("/easybroker/diagnostico")'
next_route = '@app.post("/easybroker/import-all")'
if route_start in source:
    start = source.index(route_start)
    end = source.index(next_route, start)
    source = source[:start] + source[end:]
elif 'async def easybroker_diagnostico(' in source:
    raise SystemExit("unexpected partially extracted EasyBroker diagnostics route")

for legacy in (
    '@app.get("/easybroker/diagnostico")',
    'async def easybroker_diagnostico(',
):
    if legacy in source:
        raise SystemExit(f"EasyBroker diagnostics symbol remains in main: {legacy}")
if source.count('app.include_router(easybroker_diagnostics_router)') != 1:
    raise SystemExit("EasyBroker diagnostics router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
