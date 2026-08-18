from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Colonias AVM vía Google Places.\nfrom routers.avm_places import router as avm_places_router\napp.include_router(avm_places_router)\n'''
mount_block = mount_anchor + '''\n# Comparables AVM cercanos vía Supabase/PostGIS.\nfrom routers.avm_nearby import router as avm_nearby_router\napp.include_router(avm_nearby_router)\n'''
if source.count('from routers.avm_nearby import router as avm_nearby_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected AVM nearby mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.avm_nearby import router as avm_nearby_router') != 1:
    raise SystemExit("unexpected AVM nearby mount state")

start_marker = '''# ────────────────────────────────────────────\n# AVM — COLONIAS (Nominatim) Y COMPARABLES CERCANOS (Supabase)\n'''
end_marker = '''# ─── LIMPIEZA DE IMÁGENES ─────────────────────────────────────────────────────\n'''
if '@app.post("/api/comparables-cercanos")' in source:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    source = source[:start] + end_marker + source[end + len(end_marker):]
elif 'async def comparables_cercanos(' in source or 'class CercanosRequest(' in source:
    raise SystemExit("unexpected partially extracted AVM nearby block")

for legacy in (
    '@app.post("/api/comparables-cercanos")',
    'async def comparables_cercanos(',
    'class CercanosRequest(',
    'TIPO_MAP_DB = {',
):
    if legacy in source:
        raise SystemExit(f"AVM nearby symbol remains in main: {legacy}")
if source.count('app.include_router(avm_nearby_router)') != 1:
    raise SystemExit("AVM nearby router not mounted exactly once")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
