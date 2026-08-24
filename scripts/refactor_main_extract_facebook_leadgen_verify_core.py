"""Deterministically extract GET /facebook/leadgen/webhook from main.py."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER_IMPORT = "from routers.facebook_leadgen_verify import router as facebook_leadgen_verify_router\n"
ROUTER_MOUNT = "app.include_router(facebook_leadgen_verify_router)\n"
ROUTE = "/facebook/leadgen/webhook"


def decorator_route(node: ast.AST) -> tuple[str, str] | None:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return None
    for dec in node.decorator_list:
        if not isinstance(dec, ast.Call) or not isinstance(dec.func, ast.Attribute):
            continue
        if not isinstance(dec.func.value, ast.Name) or dec.func.value.id != "app":
            continue
        if dec.func.attr not in {"get", "post", "delete", "put", "patch"}:
            continue
        if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
            return dec.func.attr, dec.args[0].value
    return None


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source)
    matches = [n for n in tree.body if decorator_route(n) == ("get", ROUTE)]
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one GET {ROUTE}, found {len(matches)}")
    node = matches[0]
    if not isinstance(node, ast.AsyncFunctionDef) or node.name != "facebook_leadgen_verify":
        raise SystemExit("unexpected Lead Ads verify handler")
    if [a.arg for a in node.args.args] != ["request"]:
        raise SystemExit("unexpected Lead Ads verify signature")

    block = ast.get_source_segment(source, node) or ""
    required = (
        "FB_VERIFY_TOKEN",
        'FB_VERIFY_TOKEN no configurado: el webhook de Lead Ads está cerrado.',
        'Response(content="not configured", status_code=503)',
        'p.get("hub.mode") == "subscribe"',
        'p.get("hub.verify_token") == FB_VERIFY_TOKEN',
        'Response(content=p.get("hub.challenge", ""), media_type="text/plain")',
        'Response(content="forbidden", status_code=403)',
    )
    missing = [frag for frag in required if frag not in block]
    if missing:
        raise SystemExit(f"Lead Ads verify source contract changed: {missing}")
    if ROUTER_IMPORT.strip() in source or ROUTER_MOUNT.strip() in source:
        raise SystemExit("Lead Ads verify router already imported or mounted")

    # The POST webhook on the same path must remain in main for this cut.
    posts = [n for n in tree.body if decorator_route(n) == ("post", ROUTE)]
    if len(posts) != 1 or not isinstance(posts[0], ast.AsyncFunctionDef) or posts[0].name != "facebook_leadgen_webhook":
        raise SystemExit("Lead Ads POST webhook sibling changed")

    lines = source.splitlines(keepends=True)
    start = min([node.lineno, *[d.lineno for d in node.decorator_list]]) - 1
    del lines[start:node.end_lineno]
    transformed = "".join(lines)

    tree2 = ast.parse(transformed)
    app_nodes = [
        n for n in tree2.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "app" for t in n.targets)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id == "FastAPI"
    ]
    if len(app_nodes) != 1:
        raise SystemExit(f"expected exactly one app = FastAPI(), found {len(app_nodes)}")
    lines = transformed.splitlines(keepends=True)
    lines.insert(app_nodes[0].lineno - 1, "\n" + ROUTER_IMPORT)
    transformed = "".join(lines)

    tree3 = ast.parse(transformed)
    includes = [
        n for n in tree3.body
        if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Attribute)
        and isinstance(n.value.func.value, ast.Name)
        and n.value.func.value.id == "app"
        and n.value.func.attr == "include_router"
    ]
    if not includes:
        raise SystemExit("no app.include_router call found")
    lines = transformed.splitlines(keepends=True)
    lines.insert(max(n.end_lineno for n in includes), "\n" + ROUTER_MOUNT)
    transformed = "".join(lines)

    check = ast.parse(transformed)
    if any(decorator_route(n) == ("get", ROUTE) for n in check.body):
        raise SystemExit("Lead Ads verify GET still exists in main.py")
    post_after = [n for n in check.body if decorator_route(n) == ("post", ROUTE)]
    if len(post_after) != 1:
        raise SystemExit("Lead Ads POST webhook was altered by GET extraction")
    if transformed.count(ROUTER_IMPORT.strip()) != 1 or transformed.count(ROUTER_MOUNT.strip()) != 1:
        raise SystemExit("unexpected Lead Ads verify router wiring count")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted GET /facebook/leadgen/webhook")


if __name__ == "__main__":
    main()
