"""Guards for moving shared Facebook token lifecycle helpers out of main.py."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "facebook_token_lifecycle.py"


class FacebookTokenLifecycleExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")

    def test_main_uses_core_aliases_after_extraction(self):
        self.assertIn(
            "from core.facebook_token_lifecycle import (FB_TOKEN_DEFAULT_LIFETIME_SECONDS as _FB_TOKEN_VIDA_DEFECTO, debug_facebook_token as _fb_debug_token)",
            self.main,
        )
        self.assertNotIn("_FB_TOKEN_VIDA_DEFECTO = 60 * 24 * 3600", self.main)
        self.assertNotIn("async def _fb_debug_token(", self.main)

    def test_core_preserves_default_lifetime_and_fail_soft_debug(self):
        self.assertIn("FB_TOKEN_DEFAULT_LIFETIME_SECONDS = 60 * 24 * 3600", self.core)
        self.assertIn("async def debug_facebook_token", self.core)
        self.assertIn('"GET",\n            "debug_token"', self.core)
        self.assertIn('"input_token": token', self.core)
        self.assertIn('"access_token": f"{app_id}|{app_secret}"', self.core)
        self.assertIn("reintentos=2", self.core)
        self.assertIn("if response is None or response.status_code != 200:\n            return {}", self.core)
        self.assertIn('return (response.json() or {}).get("data") or {}', self.core)
        self.assertIn("except Exception:\n        return {}", self.core)
        self.assertNotIn("from main import", self.core)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.core, "core/facebook_token_lifecycle.py", "exec")


if __name__ == "__main__":
    unittest.main()
