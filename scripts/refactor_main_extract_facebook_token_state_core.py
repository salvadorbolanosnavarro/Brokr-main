from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

anchor = 'from core.user_access import get_user_access_state, get_user_rol\n'
imp = 'from core.facebook_tokens import facebook_token_state as _fb_estado_token\n'
if imp not in source:
    if anchor not in source:
        raise SystemExit("Facebook token-state import anchor not found")
    source = source.replace(anchor, anchor + imp, 1)

warning_line = '_FB_AVISO_DIAS = 14\n'
if source.count(warning_line) != 1:
    raise SystemExit(f"expected one legacy Facebook warning constant, found {source.count(warning_line)}")
source = source.replace(warning_line, '', 1)

start = source.find('def _fb_estado_token(meta: dict) -> dict:')
end = source.find('\n\nasync def _fb_batch(', start)
if start == -1 or end == -1:
    raise SystemExit("legacy Facebook token-state helper boundaries not found")
source = source[:start] + source[end + 2:]

for forbidden in ('def _fb_estado_token(', '_FB_AVISO_DIAS = 14'):
    if forbidden in source:
        raise SystemExit(f"legacy Facebook token-state symbol remains: {forbidden}")
for required in (
    'from core.facebook_tokens import facebook_token_state as _fb_estado_token',
    '"token": _fb_estado_token(meta)',
    'async def _fb_batch(',
):
    if required not in source:
        raise SystemExit(f"required Facebook contract missing: {required}")

compile(source, 'main.py', 'exec')
path.write_text(source, encoding='utf-8')
