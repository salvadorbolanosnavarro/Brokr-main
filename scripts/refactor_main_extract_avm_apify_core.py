from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Descripción IA para ficha manual.\nfrom routers.ficha_manual import router as ficha_manual_router\napp.include_router(ficha_manual_router)\n'''
mount_block = mount_anchor + '''\n# Comparables AVM vía Apify/Inmuebles24.\nfrom routers.avm_apify import router as avm_apify_router\napp.include_router(avm_apify_router)\n'''
if source.count('from routers.avm_apify import router as avm_apify_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected AVM Apify mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.avm_apify import router as avm_apify_router') != 1:
    raise SystemExit("unexpected AVM Apify mount state")

start_marker = '''# ────────────────────────────────────────────\n# AVM — COMPARABLES VÍA APIFY + INMUEBLES24\n'''
end_marker = '''# ────────────────────────────────────────────\n# AVM — COLONIAS (Nominatim) Y COMPARABLES CERCANOS (Supabase)\n'''
if start_marker in source:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    source = source[:start] + source[end:]
elif any(x in source for x in ('APIFY_ACTOR', 'class ComparablesRequest(', 'def construir_url_inmuebles24(', 'def normalizar_listing(', '@app.post("/api/comparables")')):
    raise SystemExit("unexpected partially extracted AVM Apify block")

for legacy in ('APIFY_ACTOR', 'class ComparablesRequest(', 'def construir_url_inmuebles24(', 'def normalizar_listing(', '@app.post("/api/comparables")'):
    if legacy in source:
        raise SystemExit(f"AVM Apify symbol remains in main: {legacy}")
if source.count('app.include_router(avm_apify_router)') != 1:
    raise SystemExit("AVM Apify router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
