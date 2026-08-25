"""Permanent guards for Facebook campaign toggle extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_campaign_toggle.py"


class FacebookCampaignToggleExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_main_delegates_campaign_toggle(self):
        self.assertNotIn('@app.post("/facebook/campaign/toggle")', self.main)
        self.assertIn(
            "from routers.facebook_campaign_toggle import router as facebook_campaign_toggle_router",
            self.main,
        )
        self.assertIn("app.include_router(facebook_campaign_toggle_router)", self.main)

    def test_router_preserves_auth_validation_and_token_lookup(self):
        router = self.router
        self.assertIn('@router.post("/facebook/campaign/toggle")', router)
        self.assertIn('user_id = await get_user_id_from_token(request)', router)
        self.assertIn('raise HTTPException(status_code=401, detail="No autenticado")', router)
        self.assertIn('campaign_id = str(body.get("campaign_id", "") or "").strip()', router)
        self.assertIn('new_status = body.get("status", "PAUSED")', router)
        self.assertIn('raise HTTPException(status_code=400, detail="campaign_id requerido")', router)
        self.assertIn('new_status not in ("ACTIVE", "PAUSED")', router)
        self.assertIn('status debe ser ACTIVE o PAUSED', router)
        self.assertIn('meta = await get_facebook_meta(user_id)', router)
        self.assertIn('raise HTTPException(status_code=400, detail="Reconecta tu Facebook.")', router)

    def test_router_preserves_child_order_batch_and_verification(self):
        router = self.router
        self.assertIn('f"{campaign_id}/adsets"', router)
        self.assertIn('f"{adset_id}/ads"', router)
        self.assertIn('if new_status == "ACTIVE":', router)
        self.assertIn('(\"anuncio\", ad_ids)', router)
        self.assertIn('(\"campaña\", [campaign_id])', router)
        self.assertIn('"body": f"status={new_status}"', router)
        self.assertIn('results = await _fb_batch(', router)
        self.assertIn('params={"fields": "status,effective_status"}', router)
        self.assertIn('actual_status = verified.get("status") or ""', router)
        self.assertIn('ok = not failures and (actual_status == new_status if actual_status else False)', router)
        self.assertIn('return JSONResponse(status_code=207, content=response_data)', router)
        self.assertIn('"fallos": failures', router)
        self.assertNotIn("from main import", router)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_campaign_toggle.py", "exec")


if __name__ == "__main__":
    unittest.main()
