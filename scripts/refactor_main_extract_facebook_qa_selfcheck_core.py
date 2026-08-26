"""Deterministically extract Meta QA selfcheck from main.py.

This transform is static only. It never imports the application or invokes the
QA endpoint, so no Meta resource is created, toggled, or deleted by the refactor.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

ROUTER_IMPORT = (
    "from routers.facebook_qa_selfcheck import router as facebook_qa_selfcheck_router\n"
)
ROUTER_INCLUDE = "app.include_router(facebook_qa_selfcheck_router)\n"

REMOVE_NAMES = {
    "FB_QA_ENABLED",
    "FB_QA_AD_ACCOUNT_ID",
    "FB_QA_PAGE_ID",
    "_qa_imagen_jpeg",
    "_qa_es_cuenta_de_pruebas",
    "facebook_qa_selfcheck",
    "_qa_probar_backoff",
}


def assigned_names(node: ast.AST) -> set[str]:
    names: set[str] = set()
    if isinstance(node, (ast.Assign, ast.AnnAssign)):
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        for target in targets:
            if isinstance(target, ast.Name):
                names.add(target.id)
    return names


def node_name(node: ast.AST) -> str | None:
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.name
    return None


def node_start_lineno(node: ast.AST) -> int:
    start = node.lineno
    decorators = getattr(node, "decorator_list", None) or []
    if decorators:
        start = min([start, *(decorator.lineno for decorator in decorators)])
    return start


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")

    if "facebook_qa_selfcheck_router" in source:
        raise SystemExit("Facebook QA selfcheck router already connected")
    if '@app.post("/facebook/qa-selfcheck")' not in source:
        raise SystemExit("Facebook QA selfcheck route not found")

    tree = ast.parse(source)
    lines = source.splitlines(keepends=True)
    spans: list[tuple[int, int]] = []
    found: set[str] = set()

    for node in tree.body:
        matched = assigned_names(node) & REMOVE_NAMES
        name = node_name(node)
        if name in REMOVE_NAMES:
            matched.add(name)
        if matched:
            if node.end_lineno is None:
                raise SystemExit(f"Missing end_lineno for {sorted(matched)}")
            spans.append((node_start_lineno(node) - 1, node.end_lineno))
            found.update(matched)

    missing = REMOVE_NAMES - found
    if missing:
        raise SystemExit(f"Facebook QA source contract changed; missing: {sorted(missing)}")

    for start, end in sorted(spans, reverse=True):
        del lines[start:end]
    updated = "".join(lines)

    app_marker = "app = FastAPI()\n"
    if app_marker not in updated:
        raise SystemExit("FastAPI app marker changed")

    updated = updated.replace(
        app_marker,
        ROUTER_IMPORT + app_marker + ROUTER_INCLUDE,
        1,
    )

    if '@app.post("/facebook/qa-selfcheck")' in updated:
        raise SystemExit("Facebook QA route still present after extraction")
    if "async def facebook_qa_selfcheck(" in updated:
        raise SystemExit("Facebook QA function still present after extraction")
    if ROUTER_IMPORT.strip() not in updated or ROUTER_INCLUDE.strip() not in updated:
        raise SystemExit("Facebook QA router wiring missing after extraction")

    ast.parse(updated)
    MAIN.write_text(updated, encoding="utf-8")
    print("extracted POST /facebook/qa-selfcheck")


if __name__ == "__main__":
    main()
