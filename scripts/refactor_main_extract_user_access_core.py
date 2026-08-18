from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

import_anchor = '''from core.telemetry import (_request_modulo, _track_anthropic, _track_gemini_image, _track_groq, track_usage)\n'''
import_line = '''from core.user_access import get_user_access_state, get_user_rol\n'''
if source.count(import_line) == 0:
    if source.count(import_anchor) != 1:
        raise SystemExit("unexpected user-access import anchor")
    source = source.replace(import_anchor, import_anchor + import_line, 1)
elif source.count(import_line) != 1:
    raise SystemExit("unexpected user-access import state")

helper_start = '''# Helper: obtiene el rol del usuario desde la tabla usuarios\n'''
profile_marker = '''# ════════════════════════════════════════════════════════════════\n# Endpoint unificado para el perfil del usuario.\n'''
if helper_start in source:
    start = source.index(helper_start)
    end = source.index(profile_marker, start)
    source = source[:start] + source[end:]
elif 'async def get_user_rol(' in source or 'async def get_user_access_state(' in source:
    raise SystemExit("unexpected partially extracted user-access helpers")

for legacy in (
    'async def get_user_rol(',
    'async def get_user_access_state(',
):
    if legacy in source:
        raise SystemExit(f"user-access helper remains in main: {legacy}")
if source.count(import_line) != 1:
    raise SystemExit("Core user-access import not present exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
