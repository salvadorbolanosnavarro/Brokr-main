#!/usr/bin/env python3
"""Make new Facebook token persistence fail closed without TOKEN_ENC_KEY."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "main.py"
TARGET = "cifrar_secreto"
REPLACEMENT = '''def cifrar_secreto(valor: str) -> str:
    """Encrypt a token before persistence; never store new credentials in cleartext."""
    if not valor:
        return valor
    if valor.startswith(_PREFIJO_CIFRADO):
        return valor
    if not _FERNET:
        raise RuntimeError("TOKEN_ENC_KEY no configurada o inválida; no se guardará el token en texto plano.")
    try:
        return _PREFIJO_CIFRADO + _FERNET.encrypt(valor.encode("utf-8")).decode("ascii")
    except Exception as e:
        raise RuntimeError("No se pudo cifrar el token de Meta; no se guardará en texto plano.") from e
'''


def transform_source(source: str) -> str:
    tree = ast.parse(source)
    nodes = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == TARGET
    ]
    if len(nodes) != 1:
        raise RuntimeError(f"Expected one {TARGET}, found {len(nodes)}")
    node = nodes[0]
    if node.end_lineno is None:
        raise RuntimeError("Encryption helper has no end line")

    original = ast.get_source_segment(source, node) or ""
    if "return valor" not in original and "no se guardará el token" not in original:
        raise RuntimeError("Unexpected Facebook token encryption helper")

    lines = source.splitlines(keepends=True)
    lines[node.lineno - 1:node.end_lineno] = [REPLACEMENT]
    transformed = "".join(lines)
    transformed = transformed.replace(
        '"TOKEN_ENC_KEY inválida (%s). Los tokens seguirán en texto plano. "',
        '"TOKEN_ENC_KEY inválida (%s). Las nuevas conexiones de Meta quedarán bloqueadas hasta corregirla. "',
        1,
    )

    parsed = ast.parse(transformed)
    new_node = next(
        n for n in parsed.body
        if isinstance(n, ast.FunctionDef) and n.name == TARGET
    )
    segment = ast.get_source_segment(transformed, new_node) or ""
    if 'raise RuntimeError("TOKEN_ENC_KEY no configurada o inválida' not in segment:
        raise RuntimeError("Fail-closed key guard missing")
    if "except Exception as e:" not in segment or "raise RuntimeError" not in segment:
        raise RuntimeError("Encryption errors still fail open")

    # Read compatibility intentionally remains unchanged: legacy cleartext rows
    # can still be consumed while new writes require encryption.
    decrypt = next(
        n for n in parsed.body
        if isinstance(n, ast.FunctionDef) and n.name == "descifrar_secreto"
    )
    decrypt_source = ast.get_source_segment(transformed, decrypt) or ""
    if 'if not valor.startswith(_PREFIJO_CIFRADO):\n        return valor' not in decrypt_source:
        raise RuntimeError("Legacy cleartext read compatibility changed")

    compile(transformed, str(SOURCE), "exec")
    return transformed


def main() -> None:
    SOURCE.write_text(transform_source(SOURCE.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
