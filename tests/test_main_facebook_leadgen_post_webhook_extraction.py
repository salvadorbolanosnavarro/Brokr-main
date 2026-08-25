"""Permanent guards for the fail-closed Facebook Lead Ads POST webhook router."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_leadgen_webhook.py"


class FacebookLeadgenPostWebhookExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_post_webhook_leaves_main_and_router_is_mounted(self):
        main = self.main
        self.assertNotIn('@app.post("/facebook/leadgen/webhook")', main)
        self.assertIn(
            "from routers.facebook_leadgen_webhook import router as facebook_leadgen_webhook_router",
            main,
        )
        self.assertIn("app.include_router(facebook_leadgen_webhook_router)", main)

    def test_router_preserves_fail_closed_signature_boundary(self):
        router = self.router
        self.assertIn("from core.facebook_leadgen_config import FB_WEBHOOK_SECRET", router)
        self.assertIn("if not FB_WEBHOOK_SECRET:", router)
        self.assertIn("return Response(status_code=503)", router)
        self.assertIn('request.headers.get("X-Hub-Signature-256", "")', router)
        self.assertIn("hmac.new(", router)
        self.assertIn("hashlib.sha256", router)
        self.assertIn("hmac.compare_digest(firma, esperada)", router)
        self.assertIn("return Response(status_code=403)", router)

    def test_router_preserves_fail_soft_payload_and_background_contract(self):
        router = self.router
        self.assertIn("payload = json.loads(raw)", router)
        self.assertIn("except Exception:\n        return Response(status_code=200)", router)
        self.assertIn('if cambio.get("field") != "leadgen":', router)
        self.assertIn('if valor.get("leadgen_id"):', router)
        self.assertIn("background.add_task(process_facebook_lead, valor)", router)
        self.assertTrue(router.rstrip().endswith("return Response(status_code=200)"))
        self.assertNotIn("from main import", router)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_leadgen_webhook.py", "exec")


if __name__ == "__main__":
    unittest.main()
