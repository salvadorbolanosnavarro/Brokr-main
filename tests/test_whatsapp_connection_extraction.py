from pathlib import Path
import unittest

import routers.whatsapp_connection as connection
from scripts.refactor_whatsapp_extract_connection_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
CONNECTION = ROOT / "routers" / "whatsapp_connection.py"


class WhatsAppConnectionContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CONNECTION.read_text(encoding="utf-8")

    def test_operational_secrets_fail_closed_before_meta_oauth(self):
        fn_start = self.source.index("async def wa2_connect")
        oauth = self.source.index("/oauth/access_token", fn_start)
        verify_guard = self.source.index("if not WA2_VERIFY_TOKEN:", fn_start)
        pin_guard = self.source.index("if not req.coexistence and not WA2_REGISTER_PIN:", fn_start)
        self.assertLess(verify_guard, oauth)
        self.assertLess(pin_guard, oauth)
        self.assertIn('status_code=503, detail="WA2_VERIFY_TOKEN no configurado"', self.source)
        self.assertIn('status_code=503, detail="WA_REGISTER_PIN no configurado"', self.source)

    def test_coexistence_still_skips_register(self):
        self.assertIn("if req.coexistence:", self.source)
        self.assertIn("Coexistencia: se omite /register", self.source)
        self.assertIn('f"{GRAPH_API}/{phone_number_id}/register"', self.source)

    def test_number_listing_never_returns_stored_access_token(self):
        self.assertIn('"user_id": _in_filter(ids), "select": "*"', self.source)
        self.assertIn('r.pop("access_token", None)', self.source)

    def test_connection_router_contains_no_destructive_number_route(self):
        self.assertNotIn('@router.delete("/numeros/{numero_id}")', self.source)
        self.assertFalse(hasattr(connection, "wa2_numero_delete"))


class WhatsAppConnectionExtractionTests(unittest.TestCase):
    def test_transform_moves_non_destructive_routes_only(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertIn("from routers.whatsapp_connection import router as whatsapp_connection_router", transformed)
        self.assertIn("router.include_router(whatsapp_connection_router)", transformed)
        for forbidden in (
            "class ConnectReq",
            "async def wa2_connect",
            "async def wa2_numero_verificar",
            "async def wa2_numeros_list",
            "class NumeroPatchReq",
            "async def wa2_numero_patch",
        ):
            self.assertNotIn(forbidden, transformed)
        self.assertIn('async def wa2_numero_delete', transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
