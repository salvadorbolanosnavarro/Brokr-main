from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_delivery_status_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
MODULE = ROOT / "routers" / "whatsapp_delivery_status.py"


class WhatsAppDeliveryStatusExtractionTests(unittest.TestCase):
    def test_service_preserves_failure_handling(self):
        source = MODULE.read_text(encoding="utf-8")
        for required in (
            'val.get("statuses", [])',
            'if estado != "failed":',
            '"Mensaje NO entregado (%s): %s %s"',
            "await revisar_token(",
            '"entrega_error": (error.get("title") or "No se pudo entregar")[:200]',
            '"Un mensaje no se pudo entregar"',
            '"WhatsApp rechazó el envío. Revisa la conversación."',
        ):
            self.assertIn(required, source)

    def test_transform_replaces_status_loop_only(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertIn("await _procesar_statuses(val, numero)", transformed)
        self.assertIn("return True, trabajo", transformed)
        self.assertNotIn('for st in val.get("statuses", []):', transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
