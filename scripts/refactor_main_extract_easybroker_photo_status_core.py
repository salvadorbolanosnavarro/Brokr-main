from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

anchor = 'from core.pdf_store import _pdf_store\n'
shared_import = (
    'from core.property_photos import (FOTOS_BUCKET as _FOTOS_BUCKET, '\
    'foto_migrable as _foto_migrable, foto_ya_es_de_broquer as _foto_ya_es_de_broquer, '\
    'fotos_en_proceso as _fotos_en_proceso)\n'
)
if shared_import not in source:
    if anchor not in source:
        raise SystemExit("core import anchor not found")
    source = source.replace(anchor, anchor + shared_import, 1)

start = source.find('_FOTOS_BUCKET = "fotos-propiedades"')
end_marker = '# ── Compresión ──────────────────────────────────────────────────\n'
end = source.find(end_marker, start)
if start == -1 or end == -1:
    raise SystemExit("legacy photo constants/predicates block not found")
source = source[:start] + source[end:]

state_line = '_fotos_en_proceso = set()   # org_id que ya tienen un trabajador corriendo\n\n'
if state_line not in source:
    raise SystemExit("legacy photo worker state not found")
source = source.replace(state_line, '', 1)

route_start = source.find('@app.get("/easybroker/fotos-pendientes")')
next_route = source.find('@app.post("/easybroker/migrar-fotos")', route_start)
if route_start == -1 or next_route == -1:
    raise SystemExit("photo status route boundaries not found")
source = source[:route_start] + source[next_route:]

mount_anchor = '# Diagnóstico de la API de EasyBroker (solo lectura).\n'
mount = (
    '# Estado de migración de fotos EasyBroker.\n'
    'from routers.easybroker_photo_status import router as easybroker_photo_status_router\n'
    'app.include_router(easybroker_photo_status_router)\n\n'
)
if mount not in source:
    if mount_anchor not in source:
        raise SystemExit("EasyBroker router mount anchor not found")
    source = source.replace(mount_anchor, mount + mount_anchor, 1)

for forbidden in (
    '@app.get("/easybroker/fotos-pendientes")',
    '_FOTOS_BUCKET = "fotos-propiedades"',
    '_fotos_en_proceso = set()',
    'def _foto_ya_es_de_broquer(',
    'def _foto_migrable(',
):
    if forbidden in source:
        raise SystemExit(f"legacy photo status symbol remains: {forbidden}")

for required in (
    'FOTOS_BUCKET as _FOTOS_BUCKET',
    'foto_migrable as _foto_migrable',
    'fotos_en_proceso as _fotos_en_proceso',
    'from routers.easybroker_photo_status import router as easybroker_photo_status_router',
    '@app.post("/easybroker/migrar-fotos")',
    'async def _migrar_fotos_org(',
):
    if required not in source:
        raise SystemExit(f"required photo migration contract missing: {required}")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
