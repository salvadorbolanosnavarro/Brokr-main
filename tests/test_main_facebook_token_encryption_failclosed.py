"""Regression guard: new Meta secrets must never silently persist in plaintext."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "facebook_secrets.py"


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
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")

    def test_new_writes_fail_closed_without_encryption_key(self):
        encrypt = function_source(self.core, "encrypt_facebook_secret")

        self.assertIn("if not _FERNET:", encrypt)
        self.assertIn("raise HTTPException(", encrypt)
        self.assertIn("status_code=503", encrypt)
        self.assertNotIn("guardan en texto plano", encrypt)

    def test_encryption_errors_do_not_return_plaintext(self):
        encrypt = function_source(self.core, "encrypt_facebook_secret")

        self.assertIn("_FERNET.encrypt", encrypt)
        self.assertIn("except Exception as exc:", encrypt)
        self.assertIn(") from exc", encrypt)
        self.assertNotIn("return value", encrypt.split("except Exception as exc:", 1)[1])

    def test_legacy_plaintext_reads_remain_compatible(self):
        decrypt = function_source(self.core, "decrypt_facebook_secret")

        self.assertIn("if not value.startswith(_PREFIX):", decrypt)
        self.assertIn("return value", decrypt)

    def test_invalid_key_warning_no_longer_promises_plaintext_storage(self):
        self.assertNotIn("Los tokens seguirán en texto plano", self.core)
        self.assertNotIn("Los tokens seguirán en texto plano", self.main)

    def test_main_only_delegates_secret_crypto(self):
        self.assertIn(
            "from core.facebook_secrets import (decrypt_facebook_secret as descifrar_secreto, encrypt_facebook_secret as cifrar_secreto, facebook_secret_encryption_available)",
            self.main,
        )
        self.assertNotIn("def cifrar_secreto(", self.main)
        self.assertNotIn("def descifrar_secreto(", self.main)
        compile(self.main, "main.py", "exec")
        compile(self.core, "core/facebook_secrets.py", "exec")


if __name__ == "__main__":
    unittest.main()
