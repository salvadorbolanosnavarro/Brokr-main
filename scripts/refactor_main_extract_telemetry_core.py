from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

import_anchor = "from core.legacy_main_config import legacy_main_settings\n"
telemetry_import = (
    "from core.telemetry import (_request_modulo, _track_anthropic, "
    "_track_gemini_image, _track_groq, track_usage)\n"
)
if telemetry_import not in source:
    if source.count(import_anchor) != 1:
        raise SystemExit("unexpected telemetry import anchor")
    source = source.replace(import_anchor, import_anchor + telemetry_import, 1)
elif source.count(telemetry_import) != 1:
    raise SystemExit("unexpected telemetry Core import state")

mount_anchor = '''# INPC y UDIS desde Banxico SIE.\nfrom routers.banxico import router as banxico_router\napp.include_router(banxico_router)\n'''
mount_block = mount_anchor + '''\n# Heartbeat de uso por módulo.\nfrom routers.telemetry import router as telemetry_router\napp.include_router(telemetry_router)\n'''
if source.count('from routers.telemetry import router as telemetry_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected telemetry mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.telemetry import router as telemetry_router') != 1:
    raise SystemExit("unexpected telemetry router mount state")

start_marker = '''# ─────────────────────────────────────────────\n# TELEMETRÍA — uso de IA y tiempo por módulo\n'''
end_marker = '@app.post("/config/eb-key")'
if start_marker in source:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    source = source[:start] + source[end:]
elif '@app.post("/telemetria/sesion-modulo")' in source or 'async def track_usage(' in source:
    raise SystemExit("unexpected partially extracted telemetry state")

for legacy in (
    '@app.post("/telemetria/sesion-modulo")',
    'async def track_usage(',
    'def _track_anthropic(',
    'def _track_groq(',
    'def _track_gemini_image(',
    'def _request_modulo(',
    'PRICING_FALLBACK_BY_PROVIDER =',
    'MODULOS_VALIDOS =',
):
    if legacy in source:
        raise SystemExit(f"telemetry symbol remains in main: {legacy}")
if source.count('app.include_router(telemetry_router)') != 1:
    raise SystemExit("telemetry router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
