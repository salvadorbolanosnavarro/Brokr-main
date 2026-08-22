#!/usr/bin/env python3
"""Connect prepared routers and remove their duplicate main.py definitions.

Selection is AST-based. Every expected symbol/route must exist exactly once;
otherwise the transform fails without writing main.py.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

ROUTES = {
    "admin_user_uso": ("get", "/admin/user/{user_id}/uso"),
    "eliminar_cuenta_y_datos": ("delete", "/usuario/eliminar-cuenta"),
    "calcular_avm": ("post", "/avm"),
}
AVM_SYMBOLS = {
    "AVMRequest",
    "parse_price",
    "TIPO_MAP",
    "OP_MAP",
    "TIPO_SIMILAR",
    "get_comparables_eb",
    "APRECIACION_ANUAL",
    "ANIO_ACTUAL",
    "ajuste_hedonico",
    "calcular_avm",
}
IMPORTS = [
    "from routers.admin_usage import router as admin_usage_router\n",
    "from routers.account_delete import router as account_delete_router\n",
    "from routers.avm_legacy import router as avm_legacy_router\n",
]
INCLUDES = [
    "app.include_router(admin_usage_router)\n",
    "app.include_router(account_delete_router)\n",
    "app.include_router(avm_legacy_router)\n",
]


def assigned_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    targets = []
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    for target in targets:
        if isinstance(target, ast.Name):
            names.add(target.id)
    return names


def route_signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> tuple[str, str] | None:
    matches: list[tuple[str, str]] = []
    for deco in node.decorator_list:
        if not isinstance(deco, ast.Call) or not deco.args:
            continue
        func = deco.func
        if not isinstance(func, ast.Attribute) or not isinstance(func.value, ast.Name):
            continue
        if func.value.id != "app":
            continue
        try:
            path = ast.literal_eval(deco.args[0])
        except (ValueError, TypeError, SyntaxError):
            continue
        if isinstance(path, str):
            matches.append((func.attr.lower(), path))
    if len(matches) > 1:
        raise RuntimeError(f"multiple app route decorators on {node.name}: {matches}")
    return matches[0] if matches else None


def node_start(node: ast.AST) -> int:
    starts = [node.lineno]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        starts.extend(d.lineno for d in node.decorator_list)
    return min(starts)


def main() -> int:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))
    body = tree.body

    by_name: dict[str, list[ast.AST]] = {}
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            by_name.setdefault(node.name, []).append(node)
        for name in assigned_names(node):
            by_name.setdefault(name, []).append(node)

    required = set(ROUTES) | AVM_SYMBOLS
    selected: dict[int, ast.AST] = {}
    for name in sorted(required):
        matches = by_name.get(name, [])
        if len(matches) != 1:
            raise RuntimeError(f"expected exactly one top-level symbol {name!r}, found {len(matches)}")
        selected[id(matches[0])] = matches[0]

    for name, expected in ROUTES.items():
        node = by_name[name][0]
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            raise RuntimeError(f"route {name!r} is not a function")
        actual = route_signature(node)
        if actual != expected:
            raise RuntimeError(f"route {name!r}: expected {expected}, found {actual}")

    app_assign = [
        n for n in body
        if isinstance(n, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "app" for t in n.targets)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Name)
        and n.value.func.id == "FastAPI"
    ]
    if len(app_assign) != 1:
        raise RuntimeError(f"expected exactly one app = FastAPI(), found {len(app_assign)}")

    middleware_calls = [
        n for n in body
        if isinstance(n, ast.Expr)
        and isinstance(n.value, ast.Call)
        and isinstance(n.value.func, ast.Attribute)
        and isinstance(n.value.func.value, ast.Name)
        and n.value.func.value.id == "app"
        and n.value.func.attr == "add_middleware"
    ]
    if len(middleware_calls) != 1:
        raise RuntimeError(f"expected exactly one app.add_middleware(), found {len(middleware_calls)}")

    forbidden_aliases = {"admin_usage_router", "account_delete_router", "avm_legacy_router"}
    for node in body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname in forbidden_aliases:
                    raise RuntimeError(f"router alias already imported: {alias.asname}")
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value
            if (
                isinstance(call.func, ast.Attribute)
                and isinstance(call.func.value, ast.Name)
                and call.func.value.id == "app"
                and call.func.attr == "include_router"
                and call.args
                and isinstance(call.args[0], ast.Name)
                and call.args[0].id in forbidden_aliases
            ):
                raise RuntimeError(f"router already included: {call.args[0].id}")

    lines = source.splitlines(keepends=True)
    edits: list[tuple[int, int, list[str]]] = []
    for node in selected.values():
        if node.end_lineno is None:
            raise RuntimeError(f"missing end_lineno for {node!r}")
        edits.append((node_start(node) - 1, node.end_lineno, []))

    app_node = app_assign[0]
    edits.append((app_node.lineno - 1, app_node.lineno - 1, IMPORTS + ["\n"]))
    mw_node = middleware_calls[0]
    if mw_node.end_lineno is None:
        raise RuntimeError("missing end_lineno for app.add_middleware")
    edits.append((mw_node.end_lineno, mw_node.end_lineno, ["\n"] + INCLUDES + ["\n"]))

    for start, end, replacement in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        lines[start:end] = replacement

    transformed = "".join(lines)
    ast.parse(transformed, filename=str(MAIN))
    if transformed == source:
        raise RuntimeError("transform produced no changes")
    MAIN.write_text(transformed, encoding="utf-8")
    print("connected admin_usage, account_delete and avm_legacy via AST-selected extraction")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
