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


def loaded_names(tree: ast.AST) -> set[str]:
    return {
        node.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }


def import_binding(alias: ast.alias) -> str:
    return alias.asname or alias.name.split(".", 1)[0]


def cleanup_last_qa_dependencies(source: str) -> str:
    """Remove imports/guards whose final main.py consumer was QA selfcheck."""
    tree = ast.parse(source)
    loads = loaded_names(tree)
    lines = source.splitlines(keepends=True)
    spans: list[tuple[int, int]] = []

    targets = {
        ("core.facebook_graph", "_fb_paginate"),
        ("core.facebook_connection_store", "_get_fb_meta"),
    }
    found_targets: set[tuple[str, str]] = set()

    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        for alias in node.names:
            binding = import_binding(alias)
            key = (node.module, binding)
            if key not in targets or binding in loads:
                continue
            found_targets.add(key)
            if len(node.names) == 1:
                if node.end_lineno is None:
                    raise SystemExit(f"Missing end_lineno for dead import {binding}")
                spans.append((node.lineno - 1, node.end_lineno))
                continue

            if node.end_lineno is None:
                raise SystemExit(f"Missing end_lineno for dead import {binding}")
            matching_lines = [
                index
                for index in range(node.lineno - 1, node.end_lineno)
                if lines[index].strip().rstrip(",") == alias.name
            ]
            if len(matching_lines) != 1:
                raise SystemExit(
                    f"Expected one standalone import line for {binding}, found {len(matching_lines)}"
                )
            index = matching_lines[0]
            spans.append((index, index + 1))

    missing_targets = {
        key
        for key in targets
        if key[1] not in loads and key not in found_targets
    }
    if missing_targets:
        raise SystemExit(f"Dead QA import contract changed; missing: {sorted(missing_targets)}")

    if "Image" not in loads and "PIL_AVAILABLE" not in loads:
        pillow_guards = []
        for node in tree.body:
            if not isinstance(node, ast.Try) or node.end_lineno is None:
                continue
            names = {
                child.id
                for child in ast.walk(node)
                if isinstance(child, ast.Name)
            }
            imports_image = any(
                isinstance(child, ast.ImportFrom)
                and child.module == "PIL"
                and any(alias.name == "Image" for alias in child.names)
                for child in ast.walk(node)
            )
            if imports_image and "PIL_AVAILABLE" in names:
                pillow_guards.append(node)
        if len(pillow_guards) != 1:
            raise SystemExit(
                f"Expected one dead Pillow availability guard, found {len(pillow_guards)}"
            )
        guard = pillow_guards[0]
        spans.append((guard.lineno - 1, guard.end_lineno))

    for start, end in sorted(spans, reverse=True):
        del lines[start:end]

    updated = "".join(lines)
    ast.parse(updated)
    return updated


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
    updated = cleanup_last_qa_dependencies(updated)

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
    if "_fb_paginate," in updated:
        raise SystemExit("Dead _fb_paginate import still present after extraction")
    if "get_facebook_meta as _get_fb_meta" in updated:
        raise SystemExit("Dead _get_fb_meta import still present after extraction")
    if "from PIL import Image" in updated or "PIL_AVAILABLE" in updated:
        raise SystemExit("Dead Pillow QA runtime still present after extraction")
    if ROUTER_IMPORT.strip() not in updated or ROUTER_INCLUDE.strip() not in updated:
        raise SystemExit("Facebook QA router wiring missing after extraction")

    ast.parse(updated)
    MAIN.write_text(updated, encoding="utf-8")
    print("extracted POST /facebook/qa-selfcheck")


if __name__ == "__main__":
    main()
