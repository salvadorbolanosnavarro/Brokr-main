from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

old_core_import = ('from core.property_photos import (FOTOS_BUCKET as _FOTOS_BUCKET, '
                   'foto_migrable as _foto_migrable, foto_ya_es_de_broquer as _foto_ya_es_de_broquer, '
                   'fotos_en_proceso as _fotos_en_proceso)\n')
new_core_import = 'from core.property_photos import FOTOS_BUCKET as _FOTOS_BUCKET\n'
if old_core_import not in source:
    raise SystemExit("shared property-photo import not found")
source = source.replace(old_core_import, new_core_import, 1)

old_router_import = 'from routers.easybroker_photo_status import router as easybroker_photo_status_router\n'
new_router_import = ('from routers.easybroker_photo_status import ('
                     '_migrar_fotos_org, router as easybroker_photo_status_router)\n')
if old_router_import not in source:
    raise SystemExit("photo router import not found")
source = source.replace(old_router_import, new_router_import, 1)

start_marker = '# ════════════════════════════════════════════════════════════════\n# MIGRACIÓN DE FOTOS A STORAGE PROPIO\n'
end_marker = '# ════════════════════════════════════════════════════════════════\n# BORRADO MASIVO\n'
start = source.find(start_marker)
end = source.find(end_marker, start)
if start == -1 or end == -1:
    raise SystemExit("photo migration domain boundaries not found")
source = source[:start] + source[end:]

for forbidden in (
    'async def _migrar_fotos_org(',
    '@app.post("/easybroker/migrar-fotos")',
    'def _comprimir_imagen(',
    'async def _foto_a_storage(',
    '_FOTO_MAX_LADO = 1600',
):
    if forbidden in source:
        raise SystemExit(f"legacy photo migration symbol remains: {forbidden}")

for required in (
    'from core.property_photos import FOTOS_BUCKET as _FOTOS_BUCKET',
    'from routers.easybroker_photo_status import (_migrar_fotos_org, router as easybroker_photo_status_router)',
    'asyncio.create_task(_migrar_fotos_org(org_id_import))',
    'f"{SUPABASE_URL}/storage/v1/object/{_FOTOS_BUCKET}"',
    '@app.post("/propiedades/eliminar-masivo")',
):
    if required not in source:
        raise SystemExit(f"required post-extraction contract missing: {required}")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
