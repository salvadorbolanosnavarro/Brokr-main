from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Limpieza y edición de imágenes inmobiliarias.\nfrom routers.image_cleaner import router as image_cleaner_router\napp.include_router(image_cleaner_router)\n'''
mount_block = mount_anchor + '''\n# Recordatorios de tareas/citas en background.\nfrom routers.reminders import router as reminders_router\napp.include_router(reminders_router)\n'''
if source.count('from routers.reminders import router as reminders_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected reminders mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.reminders import router as reminders_router') != 1:
    raise SystemExit("unexpected reminders mount state")

start_marker = '''# =============================================================================\n# RECORDATORIOS DE TAREAS/CITAS\n'''
end_marker = '_MACHOTE_SELECT = ('
if '@app.on_event("startup")' in source and 'async def _iniciar_recordatorios()' in source:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    source = source[:start] + source[end:]
elif '_recordatorios_log = logging.getLogger("broquer.recordatorios")' in source:
    raise SystemExit("unexpected partially extracted reminders block")

for legacy in (
    '_recordatorios_log = logging.getLogger("broquer.recordatorios")',
    'async def _revisar_recordatorios()',
    'async def _recordatorios_loop()',
    'async def _iniciar_recordatorios()',
):
    if legacy in source:
        raise SystemExit(f"reminders symbol remains in main: {legacy}")
if source.count('app.include_router(reminders_router)') != 1:
    raise SystemExit("reminders router not mounted exactly once")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
