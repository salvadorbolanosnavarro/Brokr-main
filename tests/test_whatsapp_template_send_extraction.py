from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_template_send_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
ROUTER = ROOT / "routers" / "whatsapp_template_send.py"


class WhatsAppTemplateSendExtractionTests(unittest.TestCase):
    def test_template_send_preserves_scope_meta_error_and_history(self):
        source = ROUTER.read_text(encoding="utf-8")
        for required in (
            '@router.post("/mensajes/plantilla")',
            '"user_id": _in_filter(ids)',
            '"type": "template"',
            '"language": {"code": req.idioma}',
            'status_code=502',
            'Meta no pudo mandar la plantilla. Revisa que esté aprobada.',
            'resumen = f"[Plantilla: {req.nombre}]"',
            "await _guardar_mensaje(",
        ):
            self.assertIn(required, source)

    def test_transform_removes_root_send_endpoint(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertNotIn("class PlantillaEnviarReq", transformed)
        self.assertNotIn("async def wa2_enviar_plantilla", transformed)
        self.assertIn("whatsapp_template_send_router", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
