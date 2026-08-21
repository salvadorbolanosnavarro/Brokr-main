from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_conversation_settings_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
ROUTER = ROOT / "routers" / "whatsapp_conversation_settings.py"


class WhatsAppConversationSettingsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROUTER.read_text(encoding="utf-8")

    def test_legacy_boolean_maps_to_explicit_mode(self):
        self.assertIn('modo = "on" if req.ai_enabled else "off"', self.source)

    def test_only_three_modes_are_accepted(self):
        self.assertIn('if modo not in ("auto", "on", "off")', self.source)
        self.assertIn('detail="ia_modo debe ser auto, on u off"', self.source)

    def test_explicit_change_clears_pause_and_falls_back_to_legacy_boolean(self):
        self.assertIn('"ia_pausada_hasta": None', self.source)
        self.assertIn('if not guardado:', self.source)
        self.assertIn('{"ai_enabled": modo != "off"}', self.source)

    def test_scope_is_tenant_aware(self):
        self.assertIn('"user_id": _in_filter(ids)', self.source)
        self.assertIn('detail="Conversación no encontrada"', self.source)


class WhatsAppConversationSettingsExtractionTests(unittest.TestCase):
    def test_transform_moves_only_conversation_settings(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertIn("from routers.whatsapp_conversation_settings import router as whatsapp_conversation_settings_router", transformed)
        self.assertIn("router.include_router(whatsapp_conversation_settings_router)", transformed)
        self.assertNotIn("class ConvPatchReq", transformed)
        self.assertNotIn("async def wa2_conversacion_patch", transformed)
        self.assertIn("async def wa2_enviar_manual", transformed)
        self.assertIn("async def wa2_lectura", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
