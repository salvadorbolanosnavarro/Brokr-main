from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Cuadrícula pública de Instagram para el landing.\nfrom routers.instagram import router as instagram_router\napp.include_router(instagram_router)\n'''
mount_block = mount_anchor + '''\n# Captura pública de leads desde los sitios de agentes.\nfrom routers.public_site_leads import router as public_site_leads_router\napp.include_router(public_site_leads_router)\n'''
if source.count('from routers.public_site_leads import router as public_site_leads_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected public-site-leads mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.public_site_leads import router as public_site_leads_router') != 1:
    raise SystemExit("unexpected public-site-leads mount state")

start_marker = '''# ═══════════════════════════════════════════════════════════════════════════\n# LEADS DEL SITIO PÚBLICO DE AGENTES\n'''
if start_marker in source:
    start = source.index(start_marker)
    source = source[:start].rstrip() + "\n"
elif '@app.post("/sitio/{slug}/lead")' in source or '_SITIO_LEAD_RL = {' in source:
    raise SystemExit("unexpected partially extracted public-site-leads state")

if '@app.post("/sitio/{slug}/lead")' in source:
    raise SystemExit("public site lead endpoint remains in main")
if source.count('app.include_router(public_site_leads_router)') != 1:
    raise SystemExit("public site lead router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
