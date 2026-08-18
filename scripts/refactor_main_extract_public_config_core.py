from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Proxy de chat Groq.\nfrom routers.chat import router as chat_router\napp.include_router(chat_router)\n'''
mount_block = mount_anchor + '''\n# Configuración pública para el frontend.\nfrom routers.public_config import router as public_config_router\napp.include_router(public_config_router)\n'''
if source.count('from routers.public_config import router as public_config_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected public-config mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.public_config import router as public_config_router') != 1:
    raise SystemExit("unexpected public-config router mount state")

route = '''@app.get("/config/public")\nasync def get_public_config():\n    """Devuelve configuración pública que el frontend necesita al arrancar.\n    FB_APP_ID es un ID de app de Meta — no es secreto, puede exponerse al cliente."""\n    return {"fb_app_id": FB_APP_ID}\n\n'''
if route in source:
    source = source.replace(route, "", 1)
elif '@app.get("/config/public")' in source:
    raise SystemExit("unexpected public-config route shape")

if '@app.get("/config/public")' in source:
    raise SystemExit("public config route remains in main")
if source.count('app.include_router(public_config_router)') != 1:
    raise SystemExit("public config router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
