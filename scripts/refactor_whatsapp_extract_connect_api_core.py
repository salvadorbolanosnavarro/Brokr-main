from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
CORE = Path("routers/whatsapp_connect_api.py")
TARGET = "wa2_connect"
CORE_NAME = "wa2_connect_core"


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
old = find_fn(src_tree, TARGET)
core = find_fn(core_tree, CORE_NAME)
if dump_body(old) != dump_body(core):
    raise SystemExit("connect core body differs from whatsapp.py")

if "from routers.whatsapp_connect_api import wa2_connect_core" in src:
    raise SystemExit("connect extraction already applied")

start = min([old.lineno] + [d.lineno for d in old.decorator_list]) - 1
end = old.end_lineno
lines = src.splitlines(keepends=True)
replacement = '''from routers.whatsapp_connect_api import wa2_connect_core

@router.post("/connect")
async def wa2_connect(req: ConnectReq, request: Request):
    return await wa2_connect_core(
        req, request,
        _require_user=_require_user, META_APP_ID=META_APP_ID,
        META_APP_SECRET=META_APP_SECRET, HTTPException=HTTPException,
        httpx=httpx, GRAPH_API=GRAPH_API, log=log, _now=_now,
        datetime=datetime, timezone=timezone, sb_get=sb_get, sb_patch=sb_patch,
        sb_post=sb_post, WA2_WEBHOOK_URL=WA2_WEBHOOK_URL,
        WA2_VERIFY_TOKEN=WA2_VERIFY_TOKEN, WA2_REGISTER_PIN=WA2_REGISTER_PIN,
        TRAINING_DEFAULTS=TRAINING_DEFAULTS,
    )

'''
new = "".join(lines[:start]) + replacement + "".join(lines[end:])
ast.parse(new)
SRC.write_text(new)
