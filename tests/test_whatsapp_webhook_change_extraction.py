from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_webhook_messages_core import transform_source as messages_transform
from scripts.refactor_whatsapp_extract_coexistence_core import transform_source as coexistence_transform
from scripts.refactor_whatsapp_extract_incoming_core import transform_source as incoming_transform
from scripts.refactor_whatsapp_extract_delivery_status_core import transform_source as status_transform
from scripts.refactor_whatsapp_extract_webhook_change_core import transform_source as change_transform

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
MODULE = ROOT / "routers" / "whatsapp_webhook_change.py"


class WhatsAppWebhookChangeExtractionTests(unittest.TestCase):
    def test_change_service_preserves_processing_order(self):
        source = MODULE.read_text(encoding="utf-8")
        ordered = [
            "phone_number_id =",
            "numero = await get_numero(phone_number_id)",
            "contactos_meta =",
            "await procesar_coexistencia(val, numero)",
            'for msg in val.get("messages", []):',
            "await persistir_mensaje_entrante(msg, numero, contactos_meta)",
            "await procesar_statuses(val, numero)",
        ]
        positions = [source.index(marker) for marker in ordered]
        self.assertEqual(positions, sorted(positions))

    def test_full_persistence_transform_chain_composes(self):
        transformed = TARGET.read_text(encoding="utf-8")
        for transform in (
            messages_transform,
            coexistence_transform,
            incoming_transform,
            status_transform,
            change_transform,
        ):
            transformed = transform(transformed)
        start = transformed.index("async def _persistir_entrantes")
        end = transformed.index("async def _procesar_en_segundo_plano", start)
        body = transformed[start:end]
        self.assertIn("trabajo.extend(await _procesar_change_value(", body)
        self.assertNotIn("phone_number_id =", body)
        self.assertNotIn("_persistir_mensaje_entrante", body)
        self.assertNotIn("_procesar_statuses", body)
        compile(transformed, "whatsapp.py", "exec")

    def test_change_transform_is_idempotent_after_chain(self):
        transformed = TARGET.read_text(encoding="utf-8")
        for transform in (
            messages_transform,
            coexistence_transform,
            incoming_transform,
            status_transform,
            change_transform,
        ):
            transformed = transform(transformed)
        self.assertEqual(transformed, change_transform(transformed))


if __name__ == "__main__":
    unittest.main()
