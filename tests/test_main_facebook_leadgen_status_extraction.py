"""Permanent guards for the read-only Lead Ads status extraction."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_leadgen_status.py"


class FacebookLeadgenStatusExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_lives_only_in_router(self):
        self.assertNotIn('@app.get("/facebook/leadgen/status")', self.main)
        self.assertIn('from routers.facebook_leadgen_status import router as facebook_leadgen_status_router', self.main)
        self.assertIn('app.include_router(facebook_leadgen_status_router)', self.main)
        self.assertIn('@router.get("/facebook/leadgen/status")', self.router)
        self.assertNotIn('from main import', self.router)

    def test_auth_connection_and_config_contract_are_preserved(self):
        r = self.router
        self.assertIn('user_id = await get_user_id_from_token(request)', r)
        self.assertIn('status_code=401, detail="No autenticado"', r)
        self.assertIn('fila = await get_facebook_meta_row(user_id)', r)
        self.assertIn('"motivo": "No hay página de Facebook conectada."', r)
        self.assertIn('if not FB_VERIFY_TOKEN or not FB_WEBHOOK_SECRET:', r)
        self.assertIn('"motivo": "El servidor no tiene FB_VERIFY_TOKEN o FB_APP_SECRET configurados."', r)

    def test_meta_lookup_and_soft_failure_contract_are_preserved(self):
        r = self.router
        self.assertIn('httpx.AsyncClient(timeout=15)', r)
        self.assertIn('f"{page_id}/subscribed_apps"', r)
        self.assertIn('params={"fields": "id,name,subscribed_fields"}', r)
        self.assertIn('max_paginas=1', r)
        self.assertIn('prefix="Error consultando la suscripción"', r)
        self.assertIn('except HTTPException as e:', r)
        self.assertIn('return {"configurado": True, "suscrito": False, "motivo": str(e.detail)}', r)
        self.assertIn('"leadgen" in (a.get("subscribed_fields") or [])', r)
        self.assertIn('settings.legacy_main_frontend_url.rstrip', r)
        self.assertNotIn('page_token":', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_leadgen_status.py", "exec")


if __name__ == "__main__":
    unittest.main()
