"""Permanent guards for Facebook Lead Ads secret policy living in Core."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "facebook_leadgen_config.py"


class FacebookLeadgenConfigExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")

    def test_main_delegates_leadgen_secrets_to_core(self):
        self.assertIn(
            "from core.facebook_leadgen_config import (",
            self.main,
        )
        self.assertNotIn("FB_VERIFY_TOKEN = legacy_main_settings.fb_verify_token", self.main)
        self.assertNotIn("_FB_WEBHOOK_SECRET = legacy_main_settings.fb_webhook_secret or FB_APP_SECRET", self.main)

    def test_core_preserves_secret_source_and_fallback(self):
        c = self.core
        self.assertIn("FB_VERIFY_TOKEN = legacy_main_settings.fb_verify_token", c)
        self.assertIn("legacy_main_settings.fb_webhook_secret", c)
        self.assertIn("or settings.legacy_main_fb_app_secret", c)
        self.assertNotIn("os.getenv", c)
        self.assertNotIn("from main import", c)

    def test_fail_closed_consumers_remain_in_main_until_their_routes_move(self):
        m = self.main
        self.assertIn("if not FB_VERIFY_TOKEN:", m)
        self.assertIn("if not _FB_WEBHOOK_SECRET:", m)
        self.assertIn("hmac.compare_digest(firma, esperada)", m)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.core, "core/facebook_leadgen_config.py", "exec")


if __name__ == "__main__":
    unittest.main()
