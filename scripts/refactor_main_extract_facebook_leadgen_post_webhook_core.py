"""Deterministically extract POST /facebook/leadgen/webhook from main.py."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER_IMPORT = (
    "from routers.facebook_leadgen_webhook import router as facebook_leadgen_webhook_router\n"
)
ROUTER_MOUNT = "app.include_router(facebook_leadgen_webhook_router)\n"
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
    matches = [n for n in tree.body if decorator_route(n) == ("post", ROUTE)]
    if len(matches) != 1:
        raise SystemExit(f"expected exactly one POST {ROUTE}, found {len(matches)}")
    node = matches[0]
    if not isinstance(node, ast.AsyncFunctionDef) or node.name != "facebook_leadgen_webhook":
        raise SystemExit("unexpected Lead Ads POST webhook handler")
    if [a.arg for a in node.args.args] != ["request", "background"]:
        raise SystemExit("unexpected Lead Ads POST webhook signature")

    block = ast.get_source_segment(source, node) or ""
    required = (
        "raw = await request.body()",
        "if not _FB_WEBHOOK_SECRET:",
        "FB_APP_SECRET/FB_WEBHOOK_SECRET vacíos",
        "return Response(status_code=503)",
        'request.headers.get("X-Hub-Signature-256", "")',
        "hmac.new(_FB_WEBHOOK_SECRET.encode(), raw, hashlib.sha256).hexdigest()",
        "hmac.compare_digest(firma, esperada)",
        "return Response(status_code=403)",
        "payload = json.loads(raw)",
        "except Exception:",
        'if cambio.get("field") != "leadgen":',
        'if valor.get("leadgen_id"):',
        "background.add_task(_fb_procesar_lead, valor)",
        "return Response(status_code=200)",
    )
    missing = [fragment for fragment in required if fragment not in block]
    if missing:
        raise SystemExit(f"Lead Ads POST webhook source contract changed: {missing}")
    if ROUTER_IMPORT.strip() in source or ROUTER_MOUNT.strip() in source:
        raise SystemExit("Lead Ads POST webhook router already imported or mounted")

    # The GET verification handshake must already be outside main.py; this cut
    # deliberately removes only the POST endpoint sharing the same path.
    if any(decorator_route(n) == ("get", ROUTE) for n in tree.body):
        raise SystemExit("Lead Ads GET verification unexpectedly remains in main.py")

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
    if any(decorator_route(n) == ("post", ROUTE) for n in check.body):
        raise SystemExit("Lead Ads POST webhook route still exists in main.py")
    if transformed.count(ROUTER_IMPORT.strip()) != 1 or transformed.count(ROUTER_MOUNT.strip()) != 1:
        raise SystemExit("unexpected Lead Ads POST webhook router wiring count")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted POST /facebook/leadgen/webhook")


if __name__ == "__main__":
    main()
