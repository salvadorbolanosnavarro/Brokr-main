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
        self.assertIn("await get_numero(request, numero_id)", source)
        self.assertIn("await send_template(", source)
        self.assertIn("raise HTTPException(502, error", source)
        self.assertIn('"contenido": f"[Plantilla {payload.template_name}]"', source)
        self.assertIn('"direccion": "out"', source)
        self.assertIn('"tipo": "template"', source)

    def test_shared_transport_preserves_meta_template_payload(self):
        source = TRANSPORT.read_text(encoding="utf-8")
        self.assertIn("async def send_template(", source)
        self.assertIn('"messaging_product": "whatsapp"', source)
        self.assertIn('"type": "template"', source)
        self.assertIn('"name": template_name', source)
        self.assertIn('"language": {"code": language_code}', source)
        self.assertIn('payload["template"]["components"] = components', source)


if __name__ == "__main__":
    unittest.main()
