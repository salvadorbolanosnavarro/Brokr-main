from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_incoming_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
MODULE = ROOT / "routers" / "whatsapp_incoming.py"


class WhatsAppIncomingExtractionTests(unittest.TestCase):
    def test_service_preserves_security_cost_and_optout_order(self):
        source = MODULE.read_text(encoding="utf-8")
        ordered = [
            "msg_ts = int(msg.get(\"timestamp\") or 0)",
            '"wa_message_id": f"eq.{msg.get(\'id\')}"',
            "await materializar_mensaje(",
            "asesor = es_asesor(numero, wa_id)",
            "await guardar_archivo(",
            "await guardar_mensaje(",
            '"unread_count": (conv.get("unread_count") or 0) + 1',
            "in OPT_OUT_PALABRAS",
        ]
        positions = [source.index(marker) for marker in ordered]
        self.assertEqual(positions, sorted(positions))
        for palabra in (
            '"baja"', '"stop"', '"alto"', '"cancelar"', '"no molestar"',
            '"darme de baja"', '"no me escribas"', '"unsubscribe"',
        ):
            self.assertIn(palabra, source)
        self.assertIn('"prev_inbound_at": conv.get("last_inbound_at")', source)

    def test_transform_collapses_incoming_loop_but_keeps_delivery_anchor(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertIn("item = await _persistir_mensaje_entrante(msg, numero, contactos_meta)", transformed)
        self.assertIn("# ── Acuses de Meta", transformed)
        self.assertNotIn("Mensaje anterior a la conexión del número", transformed[transformed.index("async def _persistir_entrantes"):])
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
