from pathlib import Path
import ast

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Comparables AVM vía Apify/Inmuebles24.\nfrom routers.avm_apify import router as avm_apify_router\napp.include_router(avm_apify_router)\n'''
mount_block = mount_anchor + '''\n# Colonias AVM vía Google Places.\nfrom routers.avm_places import router as avm_places_router\napp.include_router(avm_places_router)\n'''
if source.count('from routers.avm_places import router as avm_places_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected AVM Places mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.avm_places import router as avm_places_router') != 1:
    raise SystemExit("unexpected AVM Places mount state")

tree = ast.parse(source)
remove_names = {"ColoniasRequest", "buscar_colonias"}
spans = []
for node in tree.body:
    if isinstance(node, ast.ClassDef) and node.name == "ColoniasRequest":
        spans.append((node.lineno, node.end_lineno, node.name))
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "buscar_colonias":
        start = min([node.lineno] + [d.lineno for d in node.decorator_list])
        spans.append((start, node.end_lineno, node.name))
found = {n for _, _, n in spans}
if found and found != remove_names:
    raise SystemExit(f"partial AVM Places symbols found: {sorted(found)}")
if spans:
    lines = source.splitlines(keepends=True)
    for start, end, _ in sorted(spans, reverse=True):
        del lines[start - 1:end]
        while start - 1 < len(lines) and lines[start - 1].strip() == "":
            del lines[start - 1]
    source = "".join(lines)

for legacy in ('class ColoniasRequest(', 'async def buscar_colonias(', '@app.get("/api/colonias")'):
    if legacy in source:
        raise SystemExit(f"AVM Places symbol remains in main: {legacy}")
if source.count('app.include_router(avm_places_router)') != 1:
    raise SystemExit("AVM Places router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
