"""Permanent guards for the read-only Facebook campaigns router extraction."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_campaigns.py"


class FacebookCampaignsExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_lives_only_in_router(self):
        self.assertNotIn('@app.get("/facebook/campaigns")', self.main)
        self.assertIn('from routers.facebook_campaigns import router as facebook_campaigns_router', self.main)
        self.assertIn('app.include_router(facebook_campaigns_router)', self.main)
        self.assertIn('@router.get("/facebook/campaigns")', self.router)
        self.assertNotIn('from main import', self.router)

    def test_auth_query_and_meta_contract_are_preserved(self):
        r = self.router
        self.assertIn('user_id = await get_user_id_from_token(request)', r)
        self.assertIn('status_code=401, detail="No autenticado"', r)
        self.assertIn('meta = await get_facebook_meta(user_id)', r)
        self.assertIn('status_code=400, detail="Reconecta tu Facebook."', r)
        self.assertIn('request.query_params.get("account_id", "")', r)
        self.assertIn('status_code=400, detail="account_id requerido"', r)
        self.assertIn('request.query_params.get("date_preset") or "last_7d"', r)
        self.assertIn('if date_preset not in FB_DATE_PRESETS:', r)

    def test_graph_and_degraded_insights_contract_are_preserved(self):
        r = self.router
        self.assertIn('httpx.AsyncClient(timeout=40)', r)
        self.assertIn('f"{account_id}/campaigns"', r)
        self.assertIn('max_items=200', r)
        self.assertIn('f"{account_id}/insights"', r)
        self.assertIn('"level": "campaign"', r)
        self.assertIn('FB_INSIGHTS_FIELDS + ",campaign_id"', r)
        self.assertIn('max_items=500', r)
        self.assertIn('except HTTPException as e:', r)
        self.assertIn('Insights no disponibles para %s: %s', r)
        self.assertIn('normalize_facebook_insights(fila)', r)
        self.assertIn('"con_metricas": bool(insights_por_campana)', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_campaigns.py", "exec")


if __name__ == "__main__":
    unittest.main()
