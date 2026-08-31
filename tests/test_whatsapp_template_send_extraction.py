"""Contract guards for WhatsApp template sending after transport centralization."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "routers" / "whatsapp_template_send.py"
TRANSPORT = ROOT / "routers" / "whatsapp_cloud_api.py"


class WhatsAppTemplateSendContractTests(unittest.TestCase):
    def test_wrapper_preserves_scope_meta_error_and_history(self):
        source = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("user_id = await _require_user(request)", source)
        self.assertIn("ids = await _ids_visibles(user_id)", source)
        self.assertIn('"user_id": _in_filter(ids)', source)
        self.assertIn("wamid, error = await send_template(", source)
        self.assertIn("status_code=502", source)
        self.assertIn('resumen = f"[Plantilla: {req.nombre}]"', source)
        self.assertIn("await _guardar_mensaje(", source)

    def test_shared_transport_preserves_meta_template_payload(self):
        source = TRANSPORT.read_text(encoding="utf-8")
        self.assertIn("async def send_template(", source)
        self.assertIn('"messaging_product": "whatsapp"', source)
        self.assertIn('"type": "template"', source)
        self.assertIn('"name": nombre', source)
        self.assertIn('"language": {"code": idioma}', source)
        self.assertIn('"components": componentes', source)


if __name__ == "__main__":
    unittest.main()
