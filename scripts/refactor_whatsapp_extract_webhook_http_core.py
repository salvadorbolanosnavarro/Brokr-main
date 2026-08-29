from __future__ import annotations

import ast
from pathlib import Path

SRC = Path("whatsapp.py")
CORE = Path("routers/whatsapp_webhook_http.py")
PAIRS = [
    ("wa2_verify_webhook", "wa2_verify_webhook_core"),
    ("wa2_receive_webhook", "wa2_receive_webhook_core"),
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

if "from routers.whatsapp_webhook_http import" in src:
    raise SystemExit("webhook HTTP extraction already applied")

verify = find_fn(src_tree, "wa2_verify_webhook")
receive = find_fn(src_tree, "wa2_receive_webhook")
lines = src.splitlines(keepends=True)

verify_start = verify.lineno - 2  # include decorator
verify_end = verify.end_lineno
receive_start = receive.lineno - 2  # include decorator
receive_end = receive.end_lineno

replacement = '''from routers.whatsapp_webhook_http import wa2_verify_webhook_core, wa2_receive_webhook_core

@router.get("/webhook")
def wa2_verify_webhook(request: Request):
    return wa2_verify_webhook_core(
        request, WA2_VERIFY_TOKEN=WA2_VERIFY_TOKEN, Response=Response,
    )


@router.post("/webhook")
async def wa2_receive_webhook(request: Request, background: BackgroundTasks):
    return await wa2_receive_webhook_core(
        request, background,
        WA2_APP_SECRET=WA2_APP_SECRET, log=log, Response=Response,
        hmac=hmac, hashlib=hashlib, json=json,
        _persistir_entrantes=_persistir_entrantes,
        _procesar_en_segundo_plano=_procesar_en_segundo_plano,
    )
'''

new = "".join(lines[:verify_start]) + replacement + "".join(lines[receive_end:])
ast.parse(new)
SRC.write_text(new)
