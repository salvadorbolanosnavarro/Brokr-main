"""Permanent guards for static extraction of POST /facebook/qa-selfcheck."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_qa_selfcheck.py"


class FacebookQaSelfcheckExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_and_qa_helpers_move_out_of_main(self):
        route_in_main = '@app.post("/facebook/qa-selfcheck")' in self.main
        router_imported = (
            "from routers.facebook_qa_selfcheck import router as facebook_qa_selfcheck_router"
            in self.main
        )
        router_included = "app.include_router(facebook_qa_selfcheck_router)" in self.main

        # The guard must pass in both deterministic workflow states:
        # prepared trigger (legacy route still in main) and certified extraction
        # (router connected). It must reject partial/double wiring.
        self.assertEqual(router_imported, router_included)
        self.assertNotEqual(route_in_main, router_imported)

        qa_symbols = (
            "async def facebook_qa_selfcheck(",
            "def _qa_imagen_jpeg(",
            "async def _qa_es_cuenta_de_pruebas(",
            "async def _qa_probar_backoff(",
        )
        for symbol in qa_symbols:
            self.assertEqual(symbol in self.main, route_in_main)

        self.assertIn('@router.post("/facebook/qa-selfcheck")', self.router)

    def test_three_production_safety_gates_are_preserved(self):
        router = self.router
        self.assertIn("FB_QA_ENABLED = legacy_main_settings.fb_qa_enabled", router)
        self.assertIn("FB_QA_AD_ACCOUNT_ID = legacy_main_settings.fb_qa_ad_account_id", router)
        self.assertIn("FB_QA_PAGE_ID = legacy_main_settings.fb_qa_page_id", router)
        self.assertIn("if not FB_QA_ENABLED:", router)
        self.assertIn("if not FB_QA_AD_ACCOUNT_ID:", router)
        self.assertIn("await _qa_es_cuenta_de_pruebas(client, user_token, account_id)", router)
        self.assertIn('f"{FB_APP_ID}/adaccounts"', router)
        self.assertIn('token=f"{FB_APP_ID}|{FB_APP_SECRET}"', router)
        self.assertIn("if not es_prueba:", router)
        self.assertIn('"abortado": True', router)

    def test_destructive_qa_behavior_remains_test_account_only(self):
        router = self.router
        gate_pos = router.index("if not es_prueba:")
        delete_pos = router.index('"DELETE"')
        self.assertLess(gate_pos, delete_pos)
        self.assertIn('if "limpieza" in pedidos and creados.get("campaign_id"):', router)
        self.assertIn('client, "DELETE", cid, token=user_token, reintentos=3', router)
        self.assertIn("httpx.MockTransport(responder)", router)
        self.assertIn('espera_base=0.05', router)
        self.assertIn('espera_max=0.2', router)

    def test_shared_core_dependencies_are_used(self):
        router = self.router
        self.assertIn("from core.facebook_connection_store import get_facebook_meta", router)
        self.assertIn("from core.facebook_graph import (", router)
        self.assertIn("from core.facebook_insights import (", router)
        self.assertIn("from core.facebook_token_lifecycle import debug_facebook_token", router)
        self.assertIn("from core.facebook_tokens import FACEBOOK_REQUIRED_SCOPES", router)
        self.assertNotIn("from main import", router)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/facebook_qa_selfcheck.py", "exec")


if __name__ == "__main__":
    unittest.main()
