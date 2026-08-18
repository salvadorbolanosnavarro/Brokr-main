from pathlib import Path
import ast

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Noticias inmobiliarias RSS.\nfrom routers.news import router as news_router\napp.include_router(news_router)\n'''
mount_block = mount_anchor + '''\n# Descripción IA para ficha manual.\nfrom routers.ficha_manual import router as ficha_manual_router\napp.include_router(ficha_manual_router)\n'''
if source.count('from routers.ficha_manual import router as ficha_manual_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected ficha-manual mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.ficha_manual import router as ficha_manual_router') != 1:
    raise SystemExit("unexpected ficha-manual mount state")

tree = ast.parse(source)
spans = []
for node in tree.body:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "generar_descripcion_ficha_manual":
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        spans.append((start, node.end_lineno))
if len(spans) > 1:
    raise SystemExit("multiple generar_descripcion_ficha_manual definitions")
if spans:
    lines = source.splitlines(keepends=True)
    start, end = spans[0]
    del lines[start - 1:end]
    while start - 1 < len(lines) and lines[start - 1].strip() == "":
        del lines[start - 1]
    source = "".join(lines)

if 'async def generar_descripcion_ficha_manual(' in source or '@app.post("/ficha-manual/descripcion")' in source:
    raise SystemExit("ficha-manual route remains in main")
if source.count('app.include_router(ficha_manual_router)') != 1:
    raise SystemExit("ficha-manual router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
