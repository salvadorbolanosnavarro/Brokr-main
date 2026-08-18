from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Configuración pública para el frontend.\nfrom routers.public_config import router as public_config_router\napp.include_router(public_config_router)\n'''
mount_block = mount_anchor + '''\n# Conexión EasyBroker compartida por organización.\nfrom routers.easybroker_config import get_eb_key_for_user, router as easybroker_config_router\napp.include_router(easybroker_config_router)\n'''
if source.count('from routers.easybroker_config import get_eb_key_for_user, router as easybroker_config_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected EasyBroker config mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.easybroker_config import get_eb_key_for_user, router as easybroker_config_router') != 1:
    raise SystemExit("unexpected EasyBroker config mount state")

class_block = '''class EbKeyRequest(BaseModel):\n    key: str\n\n'''
if class_block in source:
    source = source.replace(class_block, "", 1)
elif 'class EbKeyRequest(BaseModel):' in source:
    raise SystemExit("unexpected EbKeyRequest shape")

helper_start = '''# Helper: obtiene la EB key de un usuario desde Supabase\n'''
helper_end = '''# Helper: obtiene el rol del usuario desde la tabla usuarios\n'''
if helper_start in source:
    start = source.index(helper_start)
    end = source.index(helper_end, start)
    source = source[:start] + source[end:]
elif 'async def get_eb_key_for_user(' in source:
    raise SystemExit("unexpected partially extracted EasyBroker key helper")

routes_start = '@app.post("/config/eb-key")'
profile_marker = '''# ════════════════════════════════════════════════════════════════\n# Endpoint unificado para el perfil del usuario.\n'''
if routes_start in source:
    start = source.index(routes_start)
    end = source.index(profile_marker, start)
    source = source[:start] + source[end:]
elif '@app.delete("/config/eb-key")' in source or '@app.get("/config/eb-key")' in source:
    raise SystemExit("unexpected partially extracted EasyBroker config routes")

for legacy in (
    'class EbKeyRequest(BaseModel):',
    'async def get_eb_key_for_user(',
    '@app.post("/config/eb-key")',
    '@app.delete("/config/eb-key")',
    '@app.get("/config/eb-key")',
):
    if legacy in source:
        raise SystemExit(f"EasyBroker config symbol remains in main: {legacy}")
if source.count('app.include_router(easybroker_config_router)') != 1:
    raise SystemExit("EasyBroker config router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
