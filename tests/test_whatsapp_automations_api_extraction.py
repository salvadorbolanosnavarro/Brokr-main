from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_automations_api_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
ROUTER = ROOT / "routers" / "whatsapp_automations_api.py"


class WhatsAppAutomationsApiExtractionTests(unittest.TestCase):
    def test_router_preserves_recipe_limits_and_tenant_scope(self):
        source = ROUTER.read_text(encoding="utf-8")
        for required in (
            'disparador in ("palabra", "nuevo", "nuevo_3m")',
            "palabras = palabras[:15]",
            "acciones = acciones[:12]",
            "[:1000]",
            "[:40]",
            "[:6]",
            "user_id = await _require_user(request)",
            "ids = await _ids_visibles(user_id)",
            '"user_id": _in_filter(ids)',
            '@router.delete("/automatizaciones/{auto_id}")',
        ):
            self.assertIn(required, source)

    def test_transform_leaves_execution_engine_in_root(self):
        source = TARGET.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertNotIn("class AutomatizacionReq", transformed)
        self.assertNotIn("async def wa2_automatizaciones_list", transformed)
        self.assertNotIn("async def wa2_automatizacion_delete", transformed)
        self.assertIn("async def _correr_automatizaciones", transformed)
        self.assertIn("async def _flujo_ejecutar", transformed)
        self.assertIn("_AUTO_COOLDOWN_SEG = 120", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
