from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_contact_settings_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
WHATSAPP = ROOT / "whatsapp.py"
ROUTER = ROOT / "routers" / "whatsapp_contact_settings.py"


class WhatsAppContactSettingsContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROUTER.read_text(encoding="utf-8")

    def test_only_allowed_contact_fields_are_mutable(self):
        for field in ("nombre", "presupuesto", "forma_pago", "busca", "temperatura", "score", "etapa", "resumen", "opt_out"):
            self.assertIn(field, self.source)
        self.assertNotIn('"user_id" in body', self.source)
        self.assertNotIn('"numero_id" in body', self.source)

    def test_tags_are_trimmed_deduplicated_and_bounded(self):
        self.assertIn("str(e).strip()[:40]", self.source)
        self.assertIn("if t and t not in limpias", self.source)
        self.assertIn('permitido["etiquetas"] = limpias[:20]', self.source)

    def test_contact_update_is_tenant_scoped(self):
        self.assertIn('"user_id": _in_filter(ids)', self.source)
        self.assertIn('permitido["updated_at"] = _now()', self.source)


class WhatsAppContactSettingsExtractionTests(unittest.TestCase):
    def test_transform_moves_only_contact_patch(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        transformed = transform_source(source)
        self.assertIn("from routers.whatsapp_contact_settings import router as whatsapp_contact_settings_router", transformed)
        self.assertIn("router.include_router(whatsapp_contact_settings_router)", transformed)
        self.assertNotIn("async def wa2_contacto_patch", transformed)
        self.assertIn("async def wa2_agregar_nota", transformed)
        self.assertIn("async def wa2_automatizaciones_list", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        source = WHATSAPP.read_text(encoding="utf-8")
        once = transform_source(source)
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
