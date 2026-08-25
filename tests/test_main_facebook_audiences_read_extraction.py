"""Permanent guards for GET /facebook/audiences extraction."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_audiences_read.py"


class FacebookAudiencesReadExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_main_delegates_route_to_router(self):
        self.assertIn(
            "from routers.facebook_audiences_read import router as facebook_audiences_read_router",
            self.main,
        )
        self.assertIn("app.include_router(facebook_audiences_read_router)", self.main)
        self.assertNotIn('@app.get("/facebook/audiences")', self.main)

    def test_router_preserves_auth_and_connection_contract(self):
        r = self.router
        self.assertIn("user_id = await get_user_id_from_token(request)", r)
        self.assertIn('status_code=401, detail="No autenticado"', r)
        self.assertIn("meta_fb = await get_facebook_meta(user_id)", r)
        self.assertIn('user_token = meta_fb.get("user_token", "")', r)
        self.assertIn('account_id = meta_fb.get("ad_account_id", "")', r)
        self.assertIn(
            'status_code=400, detail="Reconecta tu Facebook desde tu perfil."', r
        )
        self.assertIn('account_id.startswith("act_")', r)

    def test_router_preserves_meta_query_and_response_shape(self):
        r = self.router
        self.assertIn("httpx.AsyncClient(timeout=30)", r)
        self.assertIn('f"{account_id}/customaudiences"', r)
        self.assertIn('"limit": "100"', r)
        self.assertIn('prefix="Error leyendo tus públicos"', r)
        self.assertIn('entrega = a.get("delivery_status") or {}', r)
        self.assertIn('operacion = a.get("operation_status") or {}', r)
        self.assertIn('listo = entrega.get("code") == 200', r)
        self.assertIn('"tamano_min": a.get("approximate_count_lower_bound")', r)
        self.assertIn('"tamano_max": a.get("approximate_count_upper_bound")', r)
        self.assertIn('"creado": a.get("time_created", "")', r)
        self.assertIn('return {"audiences": salida}', r)
        self.assertNotIn("from main import", r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_audiences_read.py", "exec")


if __name__ == "__main__":
    unittest.main()
