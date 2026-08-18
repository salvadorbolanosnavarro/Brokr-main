from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

import_anchor = 'from core.easybroker_mapping import _EB_LIMITE_PROPIEDADES, _EB_STATUS_DEFAULT, _EB_STATUS_MAP, _eb_to_brokr\n'
import_line = 'from core.pdf_design import theme_css_for_pdf\n'
if import_line not in source:
    if source.count(import_anchor) != 1:
        raise SystemExit("unexpected PDF design import anchor")
    source = source.replace(import_anchor, import_anchor + import_line, 1)

start_marker = '''# ════════════════════════════════════════════════════════════════\n# SISTEMA DE DISEÑO — fuente única de color para los PDFs\n'''
end_marker = 'app = FastAPI()\n'
if start_marker in source:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    source = source[:start] + source[end:]
elif '_THEME_TOKENS_FALLBACK' in source or 'def _theme_tokens()' in source or 'def theme_css_for_pdf(' in source:
    raise SystemExit("unexpected partially extracted PDF design bridge")

for legacy in ('_THEME_PATH =', '_THEME_TOKENS_FALLBACK', 'def _theme_tokens()', 'def theme_css_for_pdf('):
    if legacy in source:
        raise SystemExit(f"PDF design implementation remains in main: {legacy}")
if source.count(import_line.strip()) != 1:
    raise SystemExit("PDF design bridge not imported exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
