from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_templates_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
ROUTER = ROOT / "routers" / "whatsapp_templates.py"


class WhatsAppTemplatesExtractionTests(unittest.TestCase):
    def test_router_keeps_management_contract(self):
        source = ROUTER.read_text(encoding="utf-8")
        for required in (
            '@router.get("/plantillas")',
            '@router.post("/plantillas")',
            "user_id = await _require_user(request)",
            "ids = await _ids_visibles(user_id)",
            '"user_id": _in_filter(ids)',
            "message_templates",
            "variables_ejemplo",
            "error_user_msg",
        ):
            self.assertIn(required, source)
        self.assertNotIn('@router.post("/mensajes/plantilla")', source)

    def test_transform_moves_only_management_routes(self):
        source = TARGET.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertIn("whatsapp_templates_router", transformed)
        self.assertNotIn("async def wa2_plantillas_list", transformed)
        self.assertNotIn("async def wa2_plantilla_crear", transformed)
        self.assertIn("async def wa2_enviar_plantilla", transformed)
        self.assertIn('@router.post("/mensajes/plantilla")', transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
