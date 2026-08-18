from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

old_import = 'from core.easybroker import EB_API_KEY, EB_BASE, eb_headers\n'
new_import = 'from core.easybroker import EB_API_KEY, EB_BASE, _EB_LOTE, _EB_PAUSA_LOTE, _eb_get_reintentos, eb_headers\n'
if old_import in source:
    source = source.replace(old_import, new_import, 1)
elif new_import not in source:
    raise SystemExit("unexpected EasyBroker Core import state")

retry_start = '''# EasyBroker limita su API a 20 peticiones por segundo. Si nos pasamos,\n'''
next_route = '@app.post("/easybroker/import-all")'
if retry_start in source:
    start = source.index(retry_start)
    end = source.index(next_route, start)
    source = source[:start] + source[end:]
elif 'async def _eb_get_reintentos(' in source:
    raise SystemExit("unexpected partially extracted EasyBroker retry helper")

for legacy in (
    '_EB_REINTENTOS    = 5',
    '_EB_ESPERA_BASE   = 1.5',
    '_EB_ESPERA_MAX    = 20.0',
    'async def _eb_get_reintentos(',
):
    if legacy in source:
        raise SystemExit(f"EasyBroker retry symbol remains in main: {legacy}")
for required in ('_EB_LOTE', '_EB_PAUSA_LOTE', '_eb_get_reintentos'):
    if required not in new_import:
        raise SystemExit(f"missing EasyBroker Core import: {required}")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
