#!/usr/bin/env python3
"""Move Facebook secret-at-rest crypto out of main.py into Core."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
IMPORT_LINE = (
    "from core.facebook_secrets import (decrypt_facebook_secret as descifrar_secreto, "
    "encrypt_facebook_secret as cifrar_secreto, facebook_secret_encryption_available)\n"
)

ASSIGN_NAMES = {"_PREFIJO_CIFRADO", "_TOKEN_ENC_KEY", "_fermet_aviso_dado"}
FUNC_NAMES = {"cifrar_secreto", "descifrar_secreto"}


def assigned_name(node: ast.AST) -> str | None:
    if not isinstance(node, ast.Assign) or len(node.targets) != 1:
        return None
    target = node.targets[0]
    return target.id if isinstance(target, ast.Name) else None


def main() -> int:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))
    body = tree.body

    assignments = {name: [] for name in ASSIGN_NAMES}
    for node in body:
        name = assigned_name(node)
        if name in assignments:
            assignments[name].append(node)
    bad = {name: len(nodes) for name, nodes in assignments.items() if len(nodes) != 1}
    if bad:
        raise RuntimeError(f"Facebook secret assignment shape mismatch: {bad}")

    funcs = {
        name: [node for node in body if isinstance(node, ast.FunctionDef) and node.name == name]
        for name in FUNC_NAMES
    }
    bad_funcs = {name: len(nodes) for name, nodes in funcs.items() if len(nodes) != 1}
    if bad_funcs:
        raise RuntimeError(f"Facebook secret function shape mismatch: {bad_funcs}")

    crypto_tries = []
    for node in body:
        if not isinstance(node, ast.Try):
            continue
        text = ast.get_source_segment(source, node) or ""
        if "from cryptography.fernet import Fernet, InvalidToken" in text:
            crypto_tries.append(node)
    if len(crypto_tries) != 1:
        raise RuntimeError(f"expected one Fernet initialization try, found {len(crypto_tries)}")
    crypto_try = crypto_tries[0]

    # Five loads: two in encrypt, two in decrypt, one in encrypt-tokens.
    # Any extra use means the cut expanded beyond the characterized shape.
    fernet_loads = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load) and node.id == "_FERNET"
    ]
    if len(fernet_loads) != 5:
        raise RuntimeError(f"expected exactly five _FERNET loads, found {len(fernet_loads)}")

    encrypt_route = [
        node for node in body
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "facebook_encrypt_tokens"
    ]
    if len(encrypt_route) != 1:
        raise RuntimeError(f"expected one facebook_encrypt_tokens route, found {len(encrypt_route)}")
    route_text = ast.get_source_segment(source, encrypt_route[0]) or ""
    if "if not _FERNET:" not in route_text:
        raise RuntimeError("encrypt-tokens availability guard shape changed")

    if IMPORT_LINE.strip() in source:
        raise RuntimeError("Facebook secret Core import already present")

    app_assigns = [
        node for node in body
        if isinstance(node, ast.Assign)
        and any(isinstance(t, ast.Name) and t.id == "app" for t in node.targets)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "FastAPI"
    ]
    if len(app_assigns) != 1:
        raise RuntimeError(f"expected one app = FastAPI(), found {len(app_assigns)}")

    lines = source.splitlines(keepends=True)
    removals = [*sum(assignments.values(), []), crypto_try, *sum(funcs.values(), [])]
    edits: list[tuple[int, int, list[str]]] = []
    for node in removals:
        if node.end_lineno is None:
            raise RuntimeError(f"node missing end_lineno: {node!r}")
        edits.append((node.lineno - 1, node.end_lineno, []))

    app_node = app_assigns[0]
    edits.append((app_node.lineno - 1, app_node.lineno - 1, [IMPORT_LINE, "\n"]))
    for start, end, replacement in sorted(edits, key=lambda item: (item[0], item[1]), reverse=True):
        lines[start:end] = replacement
    transformed = "".join(lines)

    if transformed.count("if not _FERNET:") != 1:
        raise RuntimeError(
            f"expected one remaining direct _FERNET guard, found {transformed.count('if not _FERNET:')}"
        )
    transformed = transformed.replace(
        "if not _FERNET:", "if not facebook_secret_encryption_available():", 1
    )

    out_tree = ast.parse(transformed, filename=str(MAIN))
    if any(
        isinstance(node, ast.FunctionDef) and node.name in FUNC_NAMES
        for node in out_tree.body
    ):
        raise RuntimeError("Facebook secret helper definitions remain in main.py")
    for name in ASSIGN_NAMES:
        if any(assigned_name(node) == name for node in out_tree.body):
            raise RuntimeError(f"legacy secret assignment remains: {name}")
    if any(
        isinstance(node, ast.Name) and node.id == "_FERNET"
        for node in ast.walk(out_tree)
    ):
        raise RuntimeError("direct _FERNET use remains in main.py")
    if transformed.count(IMPORT_LINE.strip()) != 1:
        raise RuntimeError("Facebook secret Core import count mismatch")
    if transformed.count("cifrar_secreto(") < 2 or transformed.count("descifrar_secreto(") < 2:
        raise RuntimeError("legacy callers no longer delegate through imported aliases")
    if transformed.count("facebook_secret_encryption_available()") != 1:
        raise RuntimeError("encryption availability guard count mismatch")

    if transformed == source:
        raise RuntimeError("transform produced no changes")
    MAIN.write_text(transformed, encoding="utf-8")
    print("moved Facebook secret crypto to Core")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
