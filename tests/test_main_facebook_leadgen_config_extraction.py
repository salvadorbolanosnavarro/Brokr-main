"""Permanent guards for Facebook Lead Ads secret policy living in Core."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "facebook_leadgen_config.py"
VERIFY_ROUTER = ROOT / "routers" / "facebook_leadgen_verify.py"
SUBSCRIBE_ROUTER = ROOT / "routers" / "facebook_leadgen_subscribe.py"
POST_WEBHOOK_ROUTER = ROOT / "routers" / "facebook_leadgen_webhook.py"


class FacebookLeadgenConfigExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")
        cls.verify_router = VERIFY_ROUTER.read_text(encoding="utf-8")
        cls.subscribe_router = SUBSCRIBE_ROUTER.read_text(encoding="utf-8")
        cls.post_webhook_router = POST_WEBHOOK_ROUTER.read_text(encoding="utf-8")

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

    def test_fail_closed_verify_token_consumers_follow_extracted_routes(self):
        self.assertIn("from core.facebook_leadgen_config import FB_VERIFY_TOKEN", self.verify_router)
        self.assertIn("if not FB_VERIFY_TOKEN:", self.verify_router)
        self.assertIn("status_code=503", self.verify_router)
        self.assertIn("from core.facebook_leadgen_config import FB_VERIFY_TOKEN", self.subscribe_router)
        self.assertIn("if not FB_VERIFY_TOKEN:", self.subscribe_router)
        self.assertIn("status_code=503", self.subscribe_router)

    def test_fail_closed_hmac_consumer_follows_post_webhook_router(self):
        router = self.post_webhook_router
        self.assertIn("from core.facebook_leadgen_config import FB_WEBHOOK_SECRET", router)
        self.assertIn("if not FB_WEBHOOK_SECRET:", router)
        self.assertIn("hmac.compare_digest(firma, esperada)", router)
        self.assertIn("return Response(status_code=503)", router)
        self.assertIn("return Response(status_code=403)", router)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.core, "core/facebook_leadgen_config.py", "exec")
        compile(self.verify_router, "routers/facebook_leadgen_verify.py", "exec")
        compile(self.subscribe_router, "routers/facebook_leadgen_subscribe.py", "exec")
        compile(self.post_webhook_router, "routers/facebook_leadgen_webhook.py", "exec")


if __name__ == "__main__":
    unittest.main()
