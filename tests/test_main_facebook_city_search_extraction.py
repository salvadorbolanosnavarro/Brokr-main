"""Permanent guards for GET /facebook/city-search extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_city_search.py"


class FacebookCitySearchExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_removed_from_main_and_router_mounted(self):
        self.assertNotIn('@app.get("/facebook/city-search")', self.main)
        self.assertNotIn("async def facebook_city_search(", self.main)
        self.assertIn("from routers.facebook_city_search import router as facebook_city_search_router", self.main)
        self.assertIn("app.include_router(facebook_city_search_router)", self.main)

    def test_router_preserves_auth_short_query_and_token_contract(self):
        r = self.router
        self.assertIn('@router.get("/facebook/city-search")', r)
        self.assertIn('async def facebook_city_search(request: Request, q: str = "")', r)
        self.assertIn("user_id = await get_user_id_from_token(request)", r)
        self.assertIn('status_code=401, detail="No autenticado"', r)
        self.assertIn("if len(q) < 2:", r)
        self.assertIn('return {"results": []}', r)
        self.assertIn("meta = await get_facebook_meta(user_id)", r)
        self.assertIn('detail="Reconecta tu Facebook desde tu perfil."', r)

    def test_router_preserves_meta_search_fallback_and_projection(self):
        r = self.router
        self.assertIn('"type": "adgeolocation"', r)
        self.assertIn('"country_code": "MX"', r)
        self.assertIn('json.dumps(["city", "region"])', r)
        self.assertIn("if r is None or r.status_code != 200:", r)
        self.assertIn('status_code=502, detail="No se pudo conectar con Facebook. Intenta de nuevo."', r)
        self.assertIn('status_code=504, detail="Facebook no respondió al buscar ciudades. Intenta de nuevo."', r)
        self.assertIn('{"city", "region", "neighborhood", "subcity"}', r)
        for field in ('"key"', '"name"', '"type"', '"region"', '"country_name"'):
            self.assertIn(field, r)
        self.assertIn('return {"results": results}', r)
        self.assertNotIn("from main import", r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_city_search.py", "exec")


if __name__ == "__main__":
    unittest.main()
