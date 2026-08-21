from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_campaigns_read_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
ROUTER = ROOT / "routers" / "whatsapp_campaigns_read.py"


class WhatsAppCampaignsReadExtractionTests(unittest.TestCase):
    def test_read_router_is_scoped_and_does_not_send(self):
        source = ROUTER.read_text(encoding="utf-8")
        for required in (
            '@router.get("/etiquetas")',
            '@router.post("/campanas/audiencia")',
            '@router.get("/campanas")',
            '@router.get("/campanas/{campana_id}")',
            "ids = await _ids_visibles(user_id)",
            '"user_id": _in_filter(ids)',
            "c.get(\"opt_out\")",
            "_es_asesor(numero, c[\"wa_id\"])",
            '"tope": WA2_CAMPANA_TOPE',
        ):
            self.assertIn(required, source)
        self.assertNotIn("AsyncClient", source)
        self.assertNotIn("sb_post", source)
        self.assertNotIn("sb_patch", source)
        self.assertNotIn("sb_delete", source)

    def test_transform_preserves_campaign_send_path(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertNotIn("class CampanaAudienciaReq", transformed)
        self.assertNotIn("async def wa2_campana_detalle", transformed)
        self.assertIn("class CampanaCrearReq", transformed)
        self.assertIn("async def wa2_campana_crear", transformed)
        self.assertIn("async def _correr_campana", transformed)
        self.assertIn("_audiencia_campana", transformed)
        self.assertIn("_numero_visible", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
