"""Permanent guards for the Lead Ads webhook verification extraction."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_leadgen_verify.py"


class FacebookLeadgenVerifyExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_lives_only_in_router(self):
        self.assertNotIn('@app.get("/facebook/leadgen/webhook")', self.main)
        self.assertIn('from routers.facebook_leadgen_verify import router as facebook_leadgen_verify_router', self.main)
        self.assertIn('app.include_router(facebook_leadgen_verify_router)', self.main)
        self.assertIn('@router.get("/facebook/leadgen/webhook")', self.router)
        self.assertNotIn('from main import', self.router)

    def test_fail_closed_handshake_contract_is_preserved(self):
        r = self.router
        self.assertIn('from core.facebook_leadgen_config import FB_VERIFY_TOKEN', r)
        self.assertIn('if not FB_VERIFY_TOKEN:', r)
        self.assertIn('Response(content="not configured", status_code=503)', r)
        self.assertIn('p.get("hub.mode") == "subscribe"', r)
        self.assertIn('p.get("hub.verify_token") == FB_VERIFY_TOKEN', r)
        self.assertIn('Response(content=p.get("hub.challenge", ""), media_type="text/plain")', r)
        self.assertIn('Response(content="forbidden", status_code=403)', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_leadgen_verify.py", "exec")


if __name__ == "__main__":
    unittest.main()
