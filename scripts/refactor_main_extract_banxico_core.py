from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Estado mínimo del servicio.\nfrom routers.system import router as system_router\napp.include_router(system_router)\n'''
mount_block = mount_anchor + '''\n# INPC y UDIS desde Banxico SIE.\nfrom routers.banxico import router as banxico_router\napp.include_router(banxico_router)\n'''
if source.count('from routers.banxico import router as banxico_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected Banxico mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.banxico import router as banxico_router') != 1:
    raise SystemExit("unexpected Banxico router mount state")

start_marker = '''# ────────────────────────────────────────────\n# BANXICO SIE — INPC mensual + UDIS diaria\n'''
end_marker = '''# ────────────────────────────────────────────\n# CONFIG — EB API KEY POR USUARIO (Supabase)\n'''
if start_marker in source:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    source = source[:start] + source[end:]
elif '@app.get("/api/inpc/{anio}/{mes}")' in source or 'async def _banxico_fetch' in source:
    raise SystemExit("unexpected partially extracted Banxico state")

for legacy in ('@app.get("/api/inpc/{anio}/{mes}")', '@app.get("/api/udis/{fecha}")', 'async def _banxico_fetch'):
    if legacy in source:
        raise SystemExit(f"Banxico symbol remains in main: {legacy}")
if source.count('app.include_router(banxico_router)') != 1:
    raise SystemExit("Banxico router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
