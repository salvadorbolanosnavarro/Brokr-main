from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

import_anchor = '''from core.easybroker import EB_API_KEY, EB_BASE, _EB_LOTE, _EB_PAUSA_LOTE, _eb_get_reintentos, eb_headers\n'''
import_line = '''from core.easybroker_mapping import _EB_LIMITE_PROPIEDADES, _EB_STATUS_DEFAULT, _EB_STATUS_MAP, _eb_to_brokr\n'''
if source.count(import_line) == 0:
    if source.count(import_anchor) != 1:
        raise SystemExit("unexpected EasyBroker mapping import anchor")
    source = source.replace(import_anchor, import_anchor + import_line, 1)
elif source.count(import_line) != 1:
    raise SystemExit("unexpected EasyBroker mapping import state")

mapping_start = '''# Mapeo: tipo EasyBroker → tipo Brokr\n'''
next_route = '@app.post("/easybroker/import-all")'
if mapping_start in source:
    start = source.index(mapping_start)
    end = source.index(next_route, start)
    source = source[:start] + source[end:]
elif 'def _eb_to_brokr(' in source or 'def _split_street(' in source:
    raise SystemExit("unexpected partially extracted EasyBroker mapping")

for legacy in (
    '_EB_TIPO_MAP = {',
    '_EB_STATUS_MAP = {',
    '_EB_STATUS_DEFAULT = [',
    '_EB_LIMITE_PROPIEDADES = 1000',
    'def _eb_to_brokr(',
    'def _split_street(',
):
    if legacy in source:
        raise SystemExit(f"EasyBroker mapping symbol remains in main: {legacy}")
if source.count(import_line) != 1:
    raise SystemExit("Core EasyBroker mapping import not present exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
