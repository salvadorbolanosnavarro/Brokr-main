from pathlib import Path
import ast

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Generación de PDF para ISR.\nfrom routers.isr_pdf import router as isr_pdf_router\napp.include_router(isr_pdf_router)\n'''
mount_block = mount_anchor + '''\n# Noticias inmobiliarias RSS.\nfrom routers.news import router as news_router\napp.include_router(news_router)\n'''
if source.count('from routers.news import router as news_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected news mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.news import router as news_router') != 1:
    raise SystemExit("unexpected news mount state")

tree = ast.parse(source)
spans = []
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "get_noticias":
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        spans.append((start, node.end_lineno))
if len(spans) > 1:
    raise SystemExit("multiple get_noticias definitions")
if spans:
    lines = source.splitlines(keepends=True)
    start, end = spans[0]
    del lines[start - 1:end]
    while start - 1 < len(lines) and lines[start - 1].strip() == "":
        del lines[start - 1]
    source = "".join(lines)

if 'async def get_noticias(' in source or '@app.get("/noticias")' in source:
    raise SystemExit("news route remains in main")
if source.count('app.include_router(news_router)') != 1:
    raise SystemExit("news router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
