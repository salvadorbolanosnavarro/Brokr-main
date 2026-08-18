from pathlib import Path
import ast

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Autocomplete de colonias desde EasyBroker.\nfrom routers.easybroker_colonias import router as easybroker_colonias_router\napp.include_router(easybroker_colonias_router)\n'''
mount_block = mount_anchor + '''\n# Descargas de PDFs generados en memoria.\nfrom routers.pdf_downloads import router as pdf_downloads_router\napp.include_router(pdf_downloads_router)\n'''
if source.count('from routers.pdf_downloads import router as pdf_downloads_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected PDF download mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.pdf_downloads import router as pdf_downloads_router') != 1:
    raise SystemExit("unexpected PDF download mount state")

tree = ast.parse(source)
targets = {"descargar_avm_pdf", "descargar_isr_pdf", "descargar_ficha_pdf"}
spans = []
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in targets:
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        spans.append((start, node.end_lineno, node.name))
found = {name for _, _, name in spans}
if found and found != targets:
    raise SystemExit(f"partial PDF download functions found: {sorted(found)}")
if spans:
    lines = source.splitlines(keepends=True)
    for start, end, _ in sorted(spans, reverse=True):
        del lines[start - 1:end]
        while start - 1 < len(lines) and lines[start - 1].strip() == "":
            del lines[start - 1]
    source = "".join(lines)

for name in targets:
    if f"async def {name}(" in source:
        raise SystemExit(f"PDF download function remains in main: {name}")
for route in ('@app.get("/avm-pdf/{token}")', '@app.get("/isr-pdf/{token}")', '@app.get("/ficha-pdf/{token}")'):
    if route in source:
        raise SystemExit(f"PDF download route remains in main: {route}")
if source.count('app.include_router(pdf_downloads_router)') != 1:
    raise SystemExit("PDF download router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
