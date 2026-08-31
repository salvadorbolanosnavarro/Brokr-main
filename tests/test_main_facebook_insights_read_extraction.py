"""Permanent guards for the read-only Facebook insights router extraction."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_insights_read.py"


class FacebookInsightsReadExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_lives_only_in_router(self):
        self.assertNotIn('@app.get("/facebook/insights")', self.main)
        self.assertIn('from routers.facebook_insights_read import router as facebook_insights_read_router', self.main)
        self.assertIn('app.include_router(facebook_insights_read_router)', self.main)
        self.assertIn('@router.get("/facebook/insights")', self.router)
        self.assertNotIn('from main import', self.router)

    def test_auth_and_query_validation_are_preserved(self):
        r = self.router
        self.assertIn('user_id = await get_user_id_from_token(request)', r)
        self.assertIn('status_code=401, detail="No autenticado"', r)
        self.assertIn('meta = await get_facebook_meta(user_id)', r)
        self.assertIn('status_code=400, detail="Reconecta tu Facebook."', r)
        self.assertIn('status_code=400, detail="object_id requerido"', r)
        self.assertIn('level not in ("account", "campaign", "adset", "ad")', r)
        self.assertIn('status_code=400, detail="level debe ser account, campaign, adset o ad"', r)
        self.assertIn('if date_preset not in FB_DATE_PRESETS:', r)
        self.assertIn('invalidos = [b for b in breakdowns_raw if b not in FB_BREAKDOWNS]', r)
        self.assertIn('Desglose no soportado:', r)

    def test_graph_projection_and_limits_are_preserved(self):
        r = self.router
        self.assertIn('FB_INSIGHTS_FIELDS + ",campaign_id,campaign_name,adset_id,adset_name,ad_id,ad_name"', r)
        self.assertIn('httpx.AsyncClient(timeout=60)', r)
        self.assertIn('f"{object_id}/insights"', r)
        self.assertIn('max_items=1000', r)
        self.assertIn('prefix="Error obteniendo métricas"', r)
        self.assertIn('normalize_facebook_insights(fila)', r)
        self.assertIn('"breakdowns": breakdowns_raw', r)
        self.assertIn('"total": len(salida)', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_insights_read.py", "exec")


if __name__ == "__main__":
    unittest.main()
