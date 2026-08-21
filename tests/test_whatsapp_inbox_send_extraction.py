from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_inbox_send_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
ROUTER = ROOT / "routers" / "whatsapp_inbox_send.py"


class WhatsAppInboxSendExtractionTests(unittest.TestCase):
    def test_manual_send_preserves_tenant_window_and_handoff_contract(self):
        source = ROUTER.read_text(encoding="utf-8")
        for required in (
            '@router.post("/mensajes")',
            '"user_id": _in_filter(ids)',
            'detail="El mensaje viene vacío."',
            "if len(texto) > WA_MAX_TEXTO",
            'error.get("code") == 131047',
            '"ventana_cerrada": True',
            "await _guardar_mensaje(",
            "await _pausar_por_respuesta_manual(conv, numero)",
        ):
            self.assertIn(required, source)

    def test_transform_moves_only_manual_send(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertNotIn("class EnviarManualReq", transformed)
        self.assertNotIn("async def wa2_enviar_manual", transformed)
        self.assertIn("class LecturaReq", transformed)
        self.assertIn("async def wa2_lectura", transformed)
        self.assertIn("async def wa2_conversacion_patch", transformed)
        self.assertIn("async def wa2_enviar_plantilla", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
