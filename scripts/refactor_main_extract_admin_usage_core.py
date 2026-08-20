#!/usr/bin/env python3
"""Extract the final legacy admin usage endpoint from main.py."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
MOUNT = '''# Uso y costo administrativo por usuario.\nfrom routers.admin_usage import router as admin_usage_router\napp.include_router(admin_usage_router)\n\n'''
ANCHOR = '# Eliminación administrativa total (aislada; nunca se invoca en la auditoría).\n'
LEGACY_IMPORT = 'from core.legacy_admin import require_legacy_admin as require_admin\n'


def _remove_function(source: str, name: str) -> str:
    tree = ast.parse(source)
    matches = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {name} function, found {len(matches)}")
    node = matches[0]
    lines = source.splitlines(keepends=True)
    start = node.lineno - 1
    # Include decorators immediately preceding the function.
    if node.decorator_list:
        start = min(d.lineno for d in node.decorator_list) - 1
    end = node.end_lineno
    # Remove trailing blank lines with the function, but no following code.
    while end < len(lines) and lines[end].strip() == "":
        end += 1
    return ''.join(lines[:start] + lines[end:])


def transform_source(source: str) -> str:
    transformed = source
    if 'async def admin_user_uso(' in transformed:
        transformed = _remove_function(transformed, 'admin_user_uso')
    elif MOUNT not in transformed:
        raise RuntimeError("admin_user_uso missing without router mount")

    if MOUNT not in transformed:
        if ANCHOR not in transformed:
            raise RuntimeError("Admin router anchor not found")
        idx = transformed.index(ANCHOR)
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    if 'async def admin_user_uso(' in transformed or '@app.get("/admin/user/{user_id}/uso")' in transformed:
        raise RuntimeError("Admin usage implementation still present in main")

    # This was the last main.py consumer of the compatibility guard.
    if 'require_admin(' not in transformed and LEGACY_IMPORT in transformed:
        transformed = transformed.replace(LEGACY_IMPORT, '', 1)

    if 'require_admin(' in transformed:
        raise RuntimeError("Unexpected legacy admin consumer remains in main")
    if LEGACY_IMPORT in transformed:
        raise RuntimeError("Dead legacy admin alias remains in main")

    compile(transformed, str(MAIN), 'exec')
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding='utf-8')
    MAIN.write_text(transform_source(source), encoding='utf-8')


if __name__ == '__main__':
    main()
