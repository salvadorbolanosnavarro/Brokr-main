#!/usr/bin/env python3
"""Extract DELETE /facebook/connection to its prepared router via bounded AST edit."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
IMPORT = "from routers.facebook_disconnect import router as facebook_disconnect_router\n"
MOUNT = "app.include_router(facebook_disconnect_router)\n"


def start(node: ast.AST) -> int:
    return min([node.lineno] + [d.lineno for d in getattr(node, "decorator_list", [])])


def main() -> int:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))
    body = tree.body

    matches = []
    for node in body:
        if not isinstance(node, ast.AsyncFunctionDef) or node.name != "facebook_disconnect":
            continue
        for deco in node.decorator_list:
            if (isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute)
                    and isinstance(deco.func.value, ast.Name) and deco.func.value.id == "app"
                    and deco.func.attr == "delete" and deco.args
                    and isinstance(deco.args[0], ast.Constant)
                    and deco.args[0].value == "/facebook/connection"):
                matches.append(node)
    if len(matches) != 1:
        raise RuntimeError(f"expected one DELETE /facebook/connection route, found {len(matches)}")
    route = matches[0]
    if [a.arg for a in route.args.args] != ["request"]:
        raise RuntimeError("unexpected facebook_disconnect signature")
    route_src = ast.get_source_segment(source, route) or ""
    required = [
        "await exigir_gestion_integraciones(request)",
        "if not SUPABASE_URL or not SUPABASE_SERVICE_KEY",
        '"user_integrations"',
        '"provider": "eq.facebook"',
        "except httpx.HTTPStatusError",
        'return {"ok": True}',
    ]
    for fragment in required:
        if fragment not in route_src:
            raise RuntimeError(f"missing expected disconnect behavior: {fragment}")
    if IMPORT.strip() in source or MOUNT.strip() in source:
        raise RuntimeError("Facebook disconnect router already connected")

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
    if any(isinstance(n, ast.AsyncFunctionDef) and n.name == "facebook_disconnect" for n in out_tree.body):
        raise RuntimeError("facebook_disconnect remains in main.py")
    if out.count(IMPORT.strip()) != 1 or out.count(MOUNT.strip()) != 1:
        raise RuntimeError("disconnect router import/mount count mismatch")
    if out == source:
        raise RuntimeError("transform produced no changes")
    MAIN.write_text(out, encoding="utf-8")
    print("extracted DELETE /facebook/connection")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
