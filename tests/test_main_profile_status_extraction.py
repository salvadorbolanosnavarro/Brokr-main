from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "profile_status.py"


class MainProfileStatusExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_profile_status_lives_only_in_router(self):
        self.assertIn('@router.get("/profile/status")', self.router)
        self.assertNotIn('@app.get("/profile/status")', self.main)
        self.assertIn('from routers.profile_status import router as profile_status_router', self.main)
        self.assertIn('app.include_router(profile_status_router)', self.main)

    def test_integrations_contract_is_preserved(self):
        r = self.router
        self.assertIn('"provider": "in.(easybroker,facebook)"', r)
        self.assertIn('"select": "provider,api_key,meta"', r)
        self.assertIn('timeout=8', r)
        self.assertIn('"configured": True', r)
        self.assertIn('"connected": True', r)
        self.assertIn('facebook_token_state(meta)', r)
        self.assertNotIn('/rest/v1/', r)

    def test_subscription_contract_uses_core_trial_policies(self):
        r = self.router
        self.assertIn('await get_user_rol(user_id)', r)
        self.assertIn('await get_org_id_for_user(user_id)', r)
        self.assertIn('status in ("active", "trialing")', r)
        self.assertIn('trial_has_expired(row.get("trial_hasta"))', r)
        self.assertIn('asyncio.create_task(expire_trial_subscription(row.get("id")))', r)
        self.assertNotIn('trial_max_available', r)

    def test_main_reuses_core_trial_aliases_for_remaining_subscription_routes(self):
        m = self.main
        self.assertIn('expire_trial_subscription as _expirar_trial_suscripcion', m)
        self.assertIn('trial_has_expired as _trial_ya_vencio', m)
        self.assertNotIn('trial_max_available', m)
        self.assertNotIn('def _trial_ya_vencio(trial_hasta) -> bool:', m)
        self.assertNotIn('async def _expirar_trial_suscripcion(sub_id) -> None:', m)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/profile_status.py", "exec")


if __name__ == "__main__":
    unittest.main()
