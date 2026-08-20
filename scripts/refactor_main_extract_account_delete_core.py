#!/usr/bin/env python3
"""Extract the self-service account deletion endpoint from main.py."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
MOUNT = '''# Eliminación irreversible de la cuenta propia (aislada; nunca se invoca en la auditoría).\nfrom routers.account_delete import router as account_delete_router\napp.include_router(account_delete_router)\n\n'''
ANCHOR = '# Eliminación administrativa total (aislada; nunca se invoca en la auditoría).\n'


def _remove_function(source: str, name: str) -> str:
    tree = ast.parse(source)
    matches = [n for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {name} function, found {len(matches)}")
    node = matches[0]
    lines = source.splitlines(keepends=True)
    start = node.lineno - 1
    if node.decorator_list:
        start = min(d.lineno for d in node.decorator_list) - 1
    end = node.end_lineno
    while end < len(lines) and lines[end].strip() == "":
        end += 1
    return ''.join(lines[:start] + lines[end:])


def transform_source(source: str) -> str:
    transformed = source
    if 'async def eliminar_cuenta_y_datos(' in transformed:
        transformed = _remove_function(transformed, 'eliminar_cuenta_y_datos')
    elif MOUNT not in transformed:
        raise RuntimeError("self-account delete endpoint missing without router mount")

    if MOUNT not in transformed:
        if ANCHOR not in transformed:
            raise RuntimeError("Account delete router anchor not found")
        idx = transformed.index(ANCHOR)
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    if 'async def eliminar_cuenta_y_datos(' in transformed:
        raise RuntimeError("Self-account delete implementation still present in main")
    if '@app.delete("/usuario/eliminar-cuenta")' in transformed:
        raise RuntimeError("Self-account delete route still mounted directly in main")

    compile(transformed, str(MAIN), 'exec')
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding='utf-8')
    MAIN.write_text(transform_source(source), encoding='utf-8')


if __name__ == '__main__':
    main()
