#!/usr/bin/env python3
"""Make new Meta token writes fail closed without breaking legacy plaintext reads.

This bounded transform changes only ``cifrar_secreto`` and the startup warning in
``main.py``. Existing plaintext rows remain readable through ``descifrar_secreto``;
new writes can never silently fall back to storing the raw token.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

NEW_FUNCTION = '''def cifrar_secreto(valor: str) -> str:\n    """Cifra un token; rechaza escrituras nuevas si el cifrado no está disponible."""\n    if not valor:\n        return valor\n    if valor.startswith(_PREFIJO_CIFRADO):\n        return valor\n    if not _FERNET:\n        raise HTTPException(\n            status_code=503,\n            detail="Cifrado de tokens de Meta no disponible. Configura TOKEN_ENC_KEY.",\n        )\n    try:\n        return _PREFIJO_CIFRADO + _FERNET.encrypt(valor.encode("utf-8")).decode("ascii")\n    except Exception as exc:\n        _fb_log.error("No se pudo cifrar el token: %s", exc)\n        raise HTTPException(\n            status_code=503,\n            detail="No se pudo proteger el token de Meta. Intenta de nuevo más tarde.",\n        ) from exc\n'''


def main() -> int:
    source = MAIN.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(MAIN))

    funcs = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "cifrar_secreto"
    ]
    if len(funcs) != 1:
        raise RuntimeError(f"expected exactly one cifrar_secreto, found {len(funcs)}")
    func = funcs[0]
    if func.end_lineno is None:
        raise RuntimeError("cifrar_secreto missing end_lineno")

    segment = ast.get_source_segment(source, func) or ""
    required = [
        "if not _FERNET:",
        "return valor",
        "_FERNET.encrypt",
        'valor.startswith(_PREFIJO_CIFRADO)',
    ]
    missing = [item for item in required if item not in segment]
    if missing:
        raise RuntimeError(f"cifrar_secreto legacy shape mismatch: missing {missing}")
    if "raise HTTPException" in segment:
        raise RuntimeError("cifrar_secreto already appears fail closed")

    decryptors = [
        node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "descifrar_secreto"
    ]
    if len(decryptors) != 1:
        raise RuntimeError(f"expected exactly one descifrar_secreto, found {len(decryptors)}")
    decrypt_segment = ast.get_source_segment(source, decryptors[0]) or ""
    if "if not valor.startswith(_PREFIJO_CIFRADO):" not in decrypt_segment or "return valor" not in decrypt_segment:
        raise RuntimeError("legacy plaintext read compatibility guard changed")

    lines = source.splitlines(keepends=True)
    lines[func.lineno - 1:func.end_lineno] = [NEW_FUNCTION, "\n"]
    transformed = "".join(lines)

    old_message = "TOKEN_ENC_KEY inválida (%s). Los tokens seguirán en texto plano. "
    new_message = "TOKEN_ENC_KEY inválida (%s). Las nuevas escrituras de tokens de Meta se rechazarán hasta corregirla. "
    if transformed.count(old_message) != 1:
        raise RuntimeError(f"expected exactly one legacy invalid-key warning, found {transformed.count(old_message)}")
    transformed = transformed.replace(old_message, new_message, 1)

    out_tree = ast.parse(transformed, filename=str(MAIN))
    out_funcs = [
        node for node in out_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "cifrar_secreto"
    ]
    if len(out_funcs) != 1:
        raise RuntimeError("post-transform cifrar_secreto count mismatch")
    out_segment = ast.get_source_segment(transformed, out_funcs[0]) or ""
    if "if not _FERNET:" not in out_segment or "status_code=503" not in out_segment:
        raise RuntimeError("missing fail-closed no-key branch")
    if "except Exception as exc:" not in out_segment or ") from exc" not in out_segment:
        raise RuntimeError("missing fail-closed encryption-error branch")
    if "guardan en texto plano" in out_segment:
        raise RuntimeError("plaintext write fallback remains")

    out_decryptors = [
        node for node in out_tree.body
        if isinstance(node, ast.FunctionDef) and node.name == "descifrar_secreto"
    ]
    if len(out_decryptors) != 1:
        raise RuntimeError("post-transform descifrar_secreto count mismatch")
    out_decrypt_segment = ast.get_source_segment(transformed, out_decryptors[0]) or ""
    if out_decrypt_segment != decrypt_segment:
        raise RuntimeError("descifrar_secreto changed unexpectedly")

    if transformed == source:
        raise RuntimeError("transform produced no changes")
    MAIN.write_text(transformed, encoding="utf-8")
    print("made Meta token encryption fail closed for new writes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
