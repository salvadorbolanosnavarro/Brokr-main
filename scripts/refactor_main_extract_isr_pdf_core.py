from pathlib import Path
import ast

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Descargas de PDFs generados en memoria.\nfrom routers.pdf_downloads import router as pdf_downloads_router\napp.include_router(pdf_downloads_router)\n'''
mount_block = mount_anchor + '''\n# Generación de PDF para ISR.\nfrom routers.isr_pdf import router as isr_pdf_router\napp.include_router(isr_pdf_router)\n'''
if source.count('from routers.isr_pdf import router as isr_pdf_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected ISR PDF mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.isr_pdf import router as isr_pdf_router') != 1:
    raise SystemExit("unexpected ISR PDF mount state")

tree = ast.parse(source)
spans = []
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "generar_isr_pdf":
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        spans.append((start, node.end_lineno))
if len(spans) > 1:
    raise SystemExit("multiple generar_isr_pdf definitions")
if spans:
    lines = source.splitlines(keepends=True)
    start, end = spans[0]
    del lines[start - 1:end]
    while start - 1 < len(lines) and lines[start - 1].strip() == "":
        del lines[start - 1]
    source = "".join(lines)

if 'async def generar_isr_pdf(' in source or '@app.post("/isr-pdf")' in source:
    raise SystemExit("ISR PDF route remains in main")
if source.count('app.include_router(isr_pdf_router)') != 1:
    raise SystemExit("ISR PDF router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
