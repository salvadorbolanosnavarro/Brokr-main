"""Permanent guards for the Lead Ads subscribe router extraction."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_leadgen_subscribe.py"


class FacebookLeadgenSubscribeExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_lives_only_in_router(self):
        self.assertNotIn('@app.post("/facebook/leadgen/subscribe")', self.main)
        self.assertIn('from routers.facebook_leadgen_subscribe import router as facebook_leadgen_subscribe_router', self.main)
        self.assertIn('app.include_router(facebook_leadgen_subscribe_router)', self.main)
        self.assertIn('@router.post("/facebook/leadgen/subscribe")', self.router)
        self.assertNotIn('from main import', self.router)

    def test_auth_and_fail_closed_config_are_preserved(self):
        r = self.router
        self.assertIn('user_id = await exigir_gestion_integraciones(request)', r)
        self.assertIn('if not FB_VERIFY_TOKEN:', r)
        self.assertIn('status_code=503', r)
        self.assertIn('Falta configurar FB_VERIFY_TOKEN en el servidor.', r)
        self.assertIn('fila = await get_facebook_meta_row(user_id)', r)
        self.assertIn('status_code=400, detail="Conecta tu página de Facebook primero."', r)

    def test_meta_subscription_confirmation_and_persistence_are_preserved(self):
        r = self.router
        self.assertIn('httpx.AsyncClient(timeout=20)', r)
        self.assertIn('"POST",', r)
        self.assertIn('f"{page_id}/subscribed_apps"', r)
        self.assertIn('json_body={"subscribed_fields": ["leadgen"]}', r)
        self.assertIn('_fb_exigir_ok(r, "No se pudo activar la captura de prospectos")', r)
        self.assertIn('params={"fields": "id,name,subscribed_fields"}', r)
        self.assertIn('max_paginas=1', r)
        self.assertIn('prefix="No se pudo verificar la suscripción"', r)
        self.assertIn('if not suscrito:', r)
        self.assertIn('status_code=502', r)
        self.assertIn('leads_retrieval aprobado', r)
        self.assertIn('"leadgen_suscrito": True', r)
        self.assertIn('datetime.now(timezone.utc).isoformat()', r)
        self.assertIn('await patch_facebook_meta(', r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_leadgen_subscribe.py", "exec")


if __name__ == "__main__":
    unittest.main()
