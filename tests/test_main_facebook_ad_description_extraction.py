"""Permanent guards for Facebook ad-description extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_ad_description.py"


class FacebookAdDescriptionExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_main_delegates_ad_description_to_router(self):
        self.assertNotIn('@app.post("/facebook/ad-description")', self.main)
        self.assertIn(
            "from routers.facebook_ad_description import router as facebook_ad_description_router",
            self.main,
        )
        self.assertIn("app.include_router(facebook_ad_description_router)", self.main)

    def test_router_preserves_auth_prompt_and_anthropic_contract(self):
        router = self.router
        self.assertIn('@router.post("/facebook/ad-description")', router)
        self.assertIn('user_id = await get_user_id_from_token(request)', router)
        self.assertIn('raise HTTPException(status_code=401, detail="No autenticado")', router)
        self.assertIn('settings.anthropic_api_key', router)
        self.assertIn('raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada")', router)
        self.assertIn('titulo = (body.get("titulo") or "").strip()', router)
        self.assertIn('mejorar = bool(body.get("mejorar"))', router)
        self.assertIn('emojis = bool(body.get("emojis"))', router)
        self.assertIn('if mejorar and titulo:', router)
        self.assertIn('"claude-sonnet-4-6"', router)
        self.assertIn('"max_tokens": 120', router)
        self.assertIn('httpx.AsyncClient(timeout=20)', router)
        self.assertIn('"anthropic-version": "2023-06-01"', router)
        self.assertIn('raise HTTPException(status_code=502, detail="Error generando descripción")', router)
        self.assertIn('_track_anthropic(', router)
        self.assertIn('"facebook-ads"', router)
        self.assertIn('"/facebook/ad-description"', router)
        self.assertIn('.strip()[:200]', router)
        self.assertIn('return {"text": text}', router)
        self.assertNotIn("from main import", router)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_ad_description.py", "exec")


if __name__ == "__main__":
    unittest.main()
