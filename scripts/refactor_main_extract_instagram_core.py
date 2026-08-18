from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Solicitud pública de demos.\nfrom routers.demo import router as demo_router\napp.include_router(demo_router)\n'''
mount_block = mount_anchor + '''\n# Cuadrícula pública de Instagram para el landing.\nfrom routers.instagram import router as instagram_router\napp.include_router(instagram_router)\n'''
if source.count('from routers.instagram import router as instagram_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected Instagram mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.instagram import router as instagram_router') != 1:
    raise SystemExit("unexpected Instagram router mount state")

start_marker = '''# ════════════════════════════════════════════════════════════════\n# Instagram — cuadrícula pública del landing\n'''
end_marker = '''# ═══════════════════════════════════════════════════════════════════════════\n# LEADS DEL SITIO PÚBLICO DE AGENTES\n'''
if start_marker in source:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    source = source[:start] + source[end:]
elif '@app.get("/instagram/feed")' in source or '_IG_CACHE = {' in source:
    raise SystemExit("unexpected partially extracted Instagram state")

if '@app.get("/instagram/feed")' in source:
    raise SystemExit("Instagram endpoint remains in main")
if source.count('app.include_router(instagram_router)') != 1:
    raise SystemExit("Instagram router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
