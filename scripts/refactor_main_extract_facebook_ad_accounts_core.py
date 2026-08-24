#!/usr/bin/env python3
"""Extract GET /facebook/ad-accounts to its prepared router via bounded AST edit."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
IMPORT = "from routers.facebook_ad_accounts import router as facebook_ad_accounts_router\n"
MOUNT = "app.include_router(facebook_ad_accounts_router)\n"


def start(node: ast.AST) -> int:
    return min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])


def main() -> int:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))
    body = tree.body

    matches = []
    for node in body:
        if not isinstance(node, ast.AsyncFunctionDef) or node.name != "facebook_ad_accounts":
            continue
        for deco in node.decorator_list:
            if (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)
                    and isinstance(deco.func.value, ast.Name) and deco.func.value.id == "app"
                    and deco.func.attr == "get" and deco.args
                    and isinstance(deco.args[0], ast.Constant)
                    and deco.args[0].value == "/facebook/ad-accounts"):
                matches.append(node)
    if len(matches) != 1:
        raise RuntimeError(f"expected one GET /facebook/ad-accounts route, found {len(matches)}")
    route = matches[0]
    if [a.arg for a in route.args.args] != ["request"]:
        raise RuntimeError("unexpected facebook_ad_accounts signature")
    src = ast.get_source_segment(source, route) or ""
    for fragment in (
        "await get_user_id_from_token(request)",
        'status_code=401, detail="No autenticado"',
        "await _get_fb_meta(user_id)",
        '"me/adaccounts"',
        '"fields": "id,name,account_status,currency"',
        'a.get("account_status", 0) == 1',
        "await _fb_batch(",
        "/promote_pages?fields=id&limit=100",
        '"currency": a.get("currency", "MXN")',
        'return {"accounts": active}',
    ):
        if fragment not in src:
            raise RuntimeError(f"missing expected ad-accounts behavior: {fragment}")
    if IMPORT.strip() in source or MOUNT.strip() in source:
        raise RuntimeError("Facebook ad-accounts router already connected")

    apps = [n for n in body if isinstance(n, ast.Assign)
            and any(isinstance(t, ast.Name) and t.id == "app" for t in n.targets)
            and isinstance(n.value, ast.Call) and isinstance(n.value.func, ast.Name)
            and n.value.func.id == "FastAPI"]
    if len(apps) != 1:
        raise RuntimeError(f"expected one app = FastAPI(), found {len(apps)}")
    includes = [n for n in body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                and isinstance(n.value.func, ast.Attribute)
                and isinstance(n.value.func.value, ast.Name)
                and n.value.func.value.id == "app" and n.value.func.attr == "include_router"]
    if not includes:
        raise RuntimeError("expected existing app.include_router calls")
    if route.end_lineno is None:
        raise RuntimeError("ad-accounts route missing end_lineno")

    lines = source.splitlines(keepends=True)
    edits = [
        (start(route) - 1, route.end_lineno, []),
        (apps[0].lineno - 1, apps[0].lineno - 1, [IMPORT, "\n"]),
        (includes[-1].end_lineno, includes[-1].end_lineno, ["\n", MOUNT]),
    ]
    for s, e, repl in sorted(edits, reverse=True):
        lines[s:e] = repl
    out = "".join(lines)
    out_tree = ast.parse(out, filename=str(MAIN))
    if any(isinstance(n, ast.AsyncFunctionDef) and n.name == "facebook_ad_accounts" for n in out_tree.body):
        raise RuntimeError("facebook_ad_accounts remains in main.py")
    if out.count(IMPORT.strip()) != 1 or out.count(MOUNT.strip()) != 1:
        raise RuntimeError("ad-accounts router import/mount count mismatch")
    if out == source:
        raise RuntimeError("transform produced no changes")
    MAIN.write_text(out, encoding="utf-8")
    print("extracted GET /facebook/ad-accounts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
