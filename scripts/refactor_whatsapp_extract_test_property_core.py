from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
CORE = Path("routers/whatsapp_test_property.py")
PAIRS = [
    ("wa2_probar", "wa2_probar_core"),
    ("_alta_inmueble", "_alta_inmueble_core"),
]


def find_fn(tree: ast.Module, name: str):
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise SystemExit(f"missing {name}")


def dump_body(node):
    return [ast.dump(x, include_attributes=False) for x in node.body]


src = SRC.read_text()
core_src = CORE.read_text()
src_tree = ast.parse(src)
core_tree = ast.parse(core_src)
for old_name, core_name in PAIRS:
    if dump_body(find_fn(src_tree, old_name)) != dump_body(find_fn(core_tree, core_name)):
        raise SystemExit(f"body mismatch: {old_name}")

if "from routers.whatsapp_test_property import" in src:
    raise SystemExit("test/property extraction already applied")

probar = find_fn(src_tree, "wa2_probar")
alta = find_fn(src_tree, "_alta_inmueble")
lines = src.splitlines(keepends=True)

repls = []
probar_start = min([probar.lineno] + [d.lineno for d in probar.decorator_list]) - 1
probar_repl = '''from routers.whatsapp_test_property import wa2_probar_core, _alta_inmueble_core

@router.post("/probar")
async def wa2_probar(req: ProbarReq, request: Request):
    return await wa2_probar_core(
        req, request,
        _require_user=_require_user, _ids_visibles=_ids_visibles,
        sb_get=sb_get, _in_filter=_in_filter, HTTPException=HTTPException,
        _entrenamiento_de=_entrenamiento_de, _perfil_agente=_perfil_agente,
        HISTORY_LIMIT=HISTORY_LIMIT, recepcion2_responde=recepcion2_responde,
        _parsear_presupuesto=_parsear_presupuesto, _buscar_inmuebles=_buscar_inmuebles,
        _texto_inmueble=_texto_inmueble,
    )
'''
repls.append((probar_start, probar.end_lineno, probar_repl))

alta_start = alta.lineno - 1
alta_repl = '''async def _alta_inmueble(user_id: str, datos: dict, wa_id: str, fotos: list | None = None) -> str | None:
    return await _alta_inmueble_core(
        user_id, datos, wa_id, fotos,
        get_org_context=get_org_context, _normaliza_mx=_normaliza_mx,
        _hora_local=_hora_local, _now=_now, sb_post=sb_post, log=log,
    )
'''
repls.append((alta_start, alta.end_lineno, alta_repl))

for start, end, repl in sorted(repls, reverse=True):
    lines[start:end] = [repl + "\n"]
new = "".join(lines)
ast.parse(new)
SRC.write_text(new)
