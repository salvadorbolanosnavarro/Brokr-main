from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_crm_bridge_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
BRIDGE = ROOT / "routers" / "whatsapp_crm_bridge.py"


class WhatsAppCrmBridgeExtractionTests(unittest.TestCase):
    def test_bridge_preserves_org_and_contact_contract(self):
        source = BRIDGE.read_text(encoding="utf-8")
        for required in (
            "get_org_context(user_id)",
            '"fuente": "WhatsApp"',
            '"es_potencial": True',
            '"etiquetas": ["WhatsApp 2.0"]',
            '"tipo"] = "arrendatario"',
            '"tipo"] = "comprador"',
            '"descripcion_privada"',
            "hora_local().strftime(\"%d/%m %H:%M\")",
        ):
            self.assertIn(required, source)

    def test_transform_reuses_bridge_callers(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertNotIn("async def _perfil_agente", transformed)
        self.assertNotIn("async def _crear_contacto_crm", transformed)
        self.assertNotIn("async def _sincronizar_contacto_crm", transformed)
        self.assertIn("_perfil_agente", transformed)
        self.assertIn("_crear_contacto_crm", transformed)
        self.assertIn("_sincronizar_contacto_crm", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
