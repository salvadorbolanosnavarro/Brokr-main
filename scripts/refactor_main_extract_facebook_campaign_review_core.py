"""Deterministically extract GET /facebook/campaign/review from main.py."""
from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER_IMPORT = "from routers.facebook_campaign_review import router as facebook_campaign_review_router\n"
ROUTER_MOUNT = "app.include_router(facebook_campaign_review_router)\n"
ROUTE = "/facebook/campaign/review"
STATUS_NAME = "_FB_ESTADOS_EFECTIVOS"


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

    routes = [n for n in tree.body if decorator_route(n) == ("get", ROUTE)]
    if len(routes) != 1:
        raise SystemExit(f"expected exactly one GET {ROUTE}, found {len(routes)}")
    route = routes[0]
    if not isinstance(route, ast.AsyncFunctionDef) or route.name != "facebook_campaign_review":
        raise SystemExit("unexpected Facebook campaign review handler")
    if [a.arg for a in route.args.args] != ["request"]:
        raise SystemExit("unexpected Facebook campaign review signature")

    status_nodes = [
        n for n in tree.body
        if isinstance(n, ast.Assign)
        and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == STATUS_NAME
    ]
    if len(status_nodes) != 1:
        raise SystemExit(f"expected exactly one {STATUS_NAME} assignment, found {len(status_nodes)}")
    status_node = status_nodes[0]

    block = ast.get_source_segment(source, route) or ""
    status_block = ast.get_source_segment(source, status_node) or ""
    required_route = (
        "get_user_id_from_token",
        "_get_fb_meta",
        "_fb_get_json",
        "_fb_paginate",
        STATUS_NAME,
        'status_code=401, detail="No autenticado"',
        'status_code=400, detail="campaign_id requerido"',
        'status_code=400, detail="Reconecta tu Facebook."',
        'httpx.AsyncClient(timeout=30)',
        'prefix="Error leyendo la campaña"',
        'prefix="Error leyendo los anuncios"',
        'ad.get("ad_review_feedback")',
        'ad.get("issues_info")',
        '"apelable": eff in ("DISAPPROVED", "WITH_ISSUES")',
        '"con_problemas": len(rechazados)',
        "selected_campaign_ids={campaign_id}",
    )
    missing = [frag for frag in required_route if frag not in block]
    if missing:
        raise SystemExit(f"Facebook campaign review source contract changed: {missing}")
    for frag in (
        '"DISAPPROVED"',
        '"WITH_ISSUES"',
        '"PENDING_BILLING_INFO"',
        '"PENDING_REVIEW"',
        '"CAMPAIGN_PAUSED"',
        '"ADSET_PAUSED"',
    ):
        if frag not in status_block:
            raise SystemExit(f"Facebook effective status table changed: missing {frag}")

    if ROUTER_IMPORT.strip() in source or ROUTER_MOUNT.strip() in source:
        raise SystemExit("Facebook campaign review router already imported or mounted")

    app_assignments = [
        n for n in tree.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "app" for t in n.targets)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id == "FastAPI"
    ]
    if len(app_assignments) != 1:
        raise SystemExit(f"expected exactly one app = FastAPI(), found {len(app_assignments)}")

    spans = []
    route_start = min([route.lineno, *[d.lineno for d in route.decorator_list]]) - 1
    spans.append((route_start, route.end_lineno))
    spans.append((status_node.lineno - 1, status_node.end_lineno))

    lines = source.splitlines(keepends=True)
    for start, end in sorted(spans, reverse=True):
        del lines[start:end]
    transformed = "".join(lines)

    tree2 = ast.parse(transformed)
    app_node = next(
        n for n in tree2.body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "app" for t in n.targets)
    )
    lines = transformed.splitlines(keepends=True)
    lines.insert(app_node.lineno - 1, "\n" + ROUTER_IMPORT)
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
    insert_after = max(n.end_lineno for n in includes)
    lines = transformed.splitlines(keepends=True)
    lines.insert(insert_after, "\n" + ROUTER_MOUNT)
    transformed = "".join(lines)

    check = ast.parse(transformed)
    if any(decorator_route(n) == ("get", ROUTE) for n in check.body):
        raise SystemExit("Facebook campaign review route still exists in main.py")
    if any(
        isinstance(n, ast.Assign)
        and len(n.targets) == 1
        and isinstance(n.targets[0], ast.Name)
        and n.targets[0].id == STATUS_NAME
        for n in check.body
    ):
        raise SystemExit("Facebook effective status table still exists in main.py")
    if transformed.count(ROUTER_IMPORT.strip()) != 1:
        raise SystemExit("unexpected Facebook campaign review router import count")
    if transformed.count(ROUTER_MOUNT.strip()) != 1:
        raise SystemExit("unexpected Facebook campaign review router mount count")

    MAIN.write_text(transformed, encoding="utf-8")
    print("extracted GET /facebook/campaign/review")


if __name__ == "__main__":
    main()
