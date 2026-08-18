from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "subscription_activate.py"


class MainSubscriptionActivateExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_lives_only_in_router(self):
        self.assertIn('@router.post("/subscription/activate")', self.router)
        self.assertNotIn('@app.post("/subscription/activate")', self.main)
        self.assertIn('app.include_router(subscription_activate_router)', self.main)

    def test_secret_and_lookup_contract_are_preserved(self):
        r = self.router
        self.assertIn('legacy_main_settings.activate_secret', r)
        self.assertIn('raise HTTPException(status_code=503, detail="Activación no disponible.")', r)
        self.assertIn('hmac.compare_digest', r)
        self.assertIn('raise HTTPException(status_code=403, detail="No autorizado.")', r)
        self.assertIn('"stripe_customer_id": f"eq.{customer_id}"', r)
        self.assertIn('"select": "id,nombre,email"', r)
        self.assertIn('except httpx.HTTPStatusError:\n        users = []', r)
        self.assertIn('raise HTTPException(status_code=404, detail=f"Usuario no encontrado para customer_id {customer_id}.")', r)

    def test_activation_write_preserves_fail_soft_http_status(self):
        r = self.router
        self.assertIn('await post_rows(', r)
        self.assertIn('"suscripciones"', r)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', r)
        self.assertIn('timeout=10', r)
        self.assertIn('except httpx.HTTPStatusError:\n        pass', r)
        self.assertNotIn('/rest/v1/', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/subscription_activate.py", "exec")


if __name__ == "__main__":
    unittest.main()
