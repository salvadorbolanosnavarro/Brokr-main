from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '# ────────────────────────────────────────────\n# COLONIAS AUTOCOMPLETE\n'
mount = (
    '# Borrado masivo de propiedades y contactos.\n'
    'from routers.bulk_delete import router as bulk_delete_router\n'
    'app.include_router(bulk_delete_router)\n\n'
)
if mount not in source:
    if mount_anchor not in source:
        raise SystemExit("bulk-delete mount anchor not found")
    source = source.replace(mount_anchor, mount + mount_anchor, 1)

start_marker = '# ════════════════════════════════════════════════════════════════\n# BORRADO MASIVO\n'
end_marker = '# ────────────────────────────────────────────\n# COLONIAS AUTOCOMPLETE\n'
start = source.find(start_marker)
end = source.find(end_marker, start)
if start == -1 or end == -1:
    raise SystemExit("bulk-delete domain boundaries not found")
source = source[:start] + source[end:]

for forbidden in (
    'async def _alcance_borrado(',
    'async def _borrar_fotos_storage(',
    '@app.post("/propiedades/eliminar-masivo")',
    '@app.post("/contactos/eliminar-masivo")',
    '_MSG_SIN_PERMISO =',
):
    if forbidden in source:
        raise SystemExit(f"legacy bulk-delete symbol remains: {forbidden}")

for required in (
    'from routers.bulk_delete import router as bulk_delete_router',
    'app.include_router(bulk_delete_router)',
    '# COLONIAS AUTOCOMPLETE',
):
    if required not in source:
        raise SystemExit(f"required post-extraction contract missing: {required}")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
