"""Regression guard: new Meta secrets must never silently persist in plaintext."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    nodes = [
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name
    ]
    if len(nodes) != 1:
        raise AssertionError(f"expected one {name}, found {len(nodes)}")
    return ast.get_source_segment(source, nodes[0]) or ""


class FacebookTokenEncryptionFailClosedTests(unittest.TestCase):
    def test_new_writes_fail_closed_without_encryption_key(self):
        source = MAIN.read_text(encoding="utf-8")
        encrypt = function_source(source, "cifrar_secreto")

        self.assertIn("if not _FERNET:", encrypt)
        self.assertIn("raise HTTPException(", encrypt)
        self.assertIn("status_code=503", encrypt)
        self.assertNotIn("guardan en texto plano", encrypt)

    def test_encryption_errors_do_not_return_plaintext(self):
        source = MAIN.read_text(encoding="utf-8")
        encrypt = function_source(source, "cifrar_secreto")

        self.assertIn("_FERNET.encrypt", encrypt)
        self.assertIn("except Exception as exc:", encrypt)
        self.assertIn(") from exc", encrypt)
        self.assertNotIn('except Exception as e:\n        _fb_log.error("No se pudo cifrar el token: %s", e)\n        return valor', encrypt)

    def test_legacy_plaintext_reads_remain_compatible(self):
        source = MAIN.read_text(encoding="utf-8")
        decrypt = function_source(source, "descifrar_secreto")

        self.assertIn("if not valor.startswith(_PREFIJO_CIFRADO):", decrypt)
        self.assertIn("return valor", decrypt)

    def test_invalid_key_warning_no_longer_promises_plaintext_storage(self):
        source = MAIN.read_text(encoding="utf-8")
        self.assertNotIn("Los tokens seguirán en texto plano", source)
        compile(source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
