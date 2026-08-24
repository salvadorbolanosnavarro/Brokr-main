"""Permanent guards for the read-only Facebook campaign review router extraction."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_campaign_review.py"


class FacebookCampaignReviewExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_lives_only_in_router(self):
        self.assertNotIn('@app.get("/facebook/campaign/review")', self.main)
        self.assertIn('from routers.facebook_campaign_review import router as facebook_campaign_review_router', self.main)
        self.assertIn('app.include_router(facebook_campaign_review_router)', self.main)
        self.assertIn('@router.get("/facebook/campaign/review")', self.router)
        self.assertNotIn('from main import', self.router)

    def test_auth_and_campaign_lookup_are_preserved(self):
        r = self.router
        self.assertIn('user_id = await get_user_id_from_token(request)', r)
        self.assertIn('status_code=401, detail="No autenticado"', r)
        self.assertIn('request.query_params.get("campaign_id")', r)
        self.assertIn('status_code=400, detail="campaign_id requerido"', r)
        self.assertIn('meta = await get_facebook_meta(user_id)', r)
        self.assertIn('status_code=400, detail="Reconecta tu Facebook."', r)
        self.assertIn('httpx.AsyncClient(timeout=30)', r)
        self.assertIn('prefix="Error leyendo la campaña"', r)
        self.assertIn('prefix="Error leyendo los anuncios"', r)

    def test_review_projection_and_rejection_semantics_are_preserved(self):
        r = self.router
        self.assertIn('"DISAPPROVED": ("error", "Rechazado por Meta")', r)
        self.assertIn('"WITH_ISSUES": ("error", "Con observaciones de Meta")', r)
        self.assertIn('"PENDING_BILLING_INFO": ("error", "Falta método de pago en la cuenta publicitaria")', r)
        self.assertIn('ad.get("ad_review_feedback")', r)
        self.assertIn('ad.get("issues_info")', r)
        self.assertIn('issue.get("error_summary") or issue.get("error_message")', r)
        self.assertIn('return list(dict.fromkeys([s for s in salida if s.strip()]))', r)
        self.assertIn('"apelable": eff in ("DISAPPROVED", "WITH_ISSUES")', r)
        self.assertIn('"con_problemas": len(rechazados)', r)
        self.assertIn('selected_campaign_ids={campaign_id}', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_campaign_review.py", "exec")


if __name__ == "__main__":
    unittest.main()
