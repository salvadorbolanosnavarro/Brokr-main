from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "subscription_status.py"


class MainSubscriptionStatusExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_routes_live_only_in_router(self):
        self.assertIn('@router.get("/subscription/status")', self.router)
        self.assertIn('@router.post("/subscription/trial-max")', self.router)
        self.assertNotIn('@app.get("/subscription/status")', self.main)
        self.assertNotIn('@app.post("/subscription/trial-max")', self.main)
        self.assertIn('app.include_router(subscription_status_router)', self.main)

    def test_status_contract_is_preserved(self):
        r = self.router
        self.assertIn('access = await get_user_access_state(user_id)', r)
        self.assertIn('"status": "desactivada"', r)
        self.assertIn('rol in ("equipo", "admin")', r)
        self.assertIn('ctx.get("org_tipo") == "empresa"', r)
        self.assertIn('await find_latest_subscription(user_id, org_id, timeout=8)', r)
        self.assertIn('trial_has_expired(row.get("trial_hasta"))', r)
        self.assertIn('asyncio.create_task(expire_trial_subscription(row.get("id")))', r)
        self.assertIn('await trial_max_available(user_id)', r)

    def test_trial_activation_contract_is_preserved(self):
        r = self.router
        self.assertIn('TRIAL_MAX_DIAS = 7', r)
        self.assertIn('exigir_cupo(request, user_id)', r)
        self.assertIn('accepted_statuses=(200, 201)', r)
        self.assertIn('{"trial_max_usado": True}', r)
        self.assertIn('except httpx.HTTPStatusError:\n        pass', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/subscription_status.py", "exec")


if __name__ == "__main__":
    unittest.main()
