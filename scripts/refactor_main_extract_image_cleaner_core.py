from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Comparables AVM cercanos vía Supabase/PostGIS.\nfrom routers.avm_nearby import router as avm_nearby_router\napp.include_router(avm_nearby_router)\n'''
mount_block = mount_anchor + '''\n# Limpieza y edición de imágenes inmobiliarias.\nfrom routers.image_cleaner import router as image_cleaner_router\napp.include_router(image_cleaner_router)\n'''
if source.count('from routers.image_cleaner import router as image_cleaner_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected image cleaner mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.image_cleaner import router as image_cleaner_router') != 1:
    raise SystemExit("unexpected image cleaner mount state")

start_marker = '# ─── LIMPIEZA DE IMÁGENES ─────────────────────────────────────────────────────\n'
end_marker = '# ════════════════════════════════════════════════════════════════\n# META GRAPH API — capa común\n'
if '@app.post("/images/clean")' in source:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    source = source[:start] + end_marker + source[end + len(end_marker):]
elif 'async def clean_images(' in source or 'def _process_image_sync(' in source:
    raise SystemExit("unexpected partially extracted image cleaner block")

for legacy in (
    '@app.post("/images/clean")',
    'async def clean_images(',
    'def _process_image_sync(',
    'async def _process_with_gemini(',
):
    if legacy in source:
        raise SystemExit(f"image cleaner symbol remains in main: {legacy}")
if source.count('app.include_router(image_cleaner_router)') != 1:
    raise SystemExit("image cleaner router not mounted exactly once")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
