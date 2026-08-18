from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Captura pública de leads desde los sitios de agentes.\nfrom routers.public_site_leads import router as public_site_leads_router\napp.include_router(public_site_leads_router)\n'''
mount_block = mount_anchor + '''\n# Estado mínimo del servicio.\nfrom routers.system import router as system_router\napp.include_router(system_router)\n'''
if source.count('from routers.system import router as system_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected system mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.system import router as system_router') != 1:
    raise SystemExit("unexpected system router mount state")

start_marker = '''# ────────────────────────────────────────────\n# EASYBROKER — BASE ENDPOINTS\n# ────────────────────────────────────────────\n'''
end_marker = '''# ────────────────────────────────────────────\n# BANXICO SIE — INPC mensual + UDIS diaria\n'''
if start_marker in source:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    source = source[:start] + source[end:]
elif '@app.get("/")' in source or 'def ping():' in source:
    raise SystemExit("unexpected partially extracted system state")

if '@app.get("/")' in source or '@app.get("/ping")' in source:
    raise SystemExit("system endpoints remain in main")
if source.count('app.include_router(system_router)') != 1:
    raise SystemExit("system router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
