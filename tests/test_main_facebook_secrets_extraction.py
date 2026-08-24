"""Permanent guards for Meta secret encryption living outside main.py."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "facebook_secrets.py"


class FacebookSecretsExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")

    def test_main_delegates_secret_crypto_to_core(self):
        self.assertIn(
            "from core.facebook_secrets import (decrypt_facebook_secret as descifrar_secreto, encrypt_facebook_secret as cifrar_secreto, facebook_secret_encryption_available)",
            self.main,
        )
        self.assertNotIn("def cifrar_secreto(", self.main)
        self.assertNotIn("def descifrar_secreto(", self.main)
        self.assertNotIn("_PREFIJO_CIFRADO =", self.main)
        self.assertNotIn("_TOKEN_ENC_KEY =", self.main)
        self.assertNotIn("_fermet_aviso_dado", self.main)
        self.assertIn("if not facebook_secret_encryption_available():", self.main)

    def test_core_preserves_fail_closed_writes_and_legacy_reads(self):
        self.assertIn("def encrypt_facebook_secret", self.core)
        self.assertIn("status_code=503", self.core)
        self.assertIn("raise HTTPException(", self.core)
        self.assertNotIn("guardan en texto plano", self.core)
        self.assertIn("def decrypt_facebook_secret", self.core)
        self.assertIn("if not value.startswith(_PREFIX):\n        return value", self.core)
        self.assertIn("def facebook_secret_encryption_available", self.core)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.core, "core/facebook_secrets.py", "exec")


if __name__ == "__main__":
    unittest.main()
