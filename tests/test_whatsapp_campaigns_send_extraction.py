from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_campaigns_read_core import transform_source as read_transform
from scripts.refactor_whatsapp_extract_campaigns_send_core import transform_source as send_transform

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
ROUTER = ROOT / "routers" / "whatsapp_campaigns_send.py"
CLOUD = ROOT / "routers" / "whatsapp_cloud_api.py"


class WhatsAppCampaignSendExtractionTests(unittest.TestCase):
    def test_router_preserves_limits_progress_history_and_push(self):
        source = ROUTER.read_text(encoding="utf-8")
        for required in (
            '@router.post("/campanas")',
            "WA2_CAMPANA_TOPE",
            'detail="No hay contactos en esa audiencia (o todos pidieron baja)."',
            '"estado": "enviando"',
            '"enviados": 0',
            '"fallidos": 0',
            "background.add_task(",
            "await asyncio.sleep(0.5)",
            "if (index + 1) % 10 == 0:",
            '"estado": "terminada"',
            'resumen = f"[Campaña · plantilla {plantilla}]"',
            '"Campaña terminada"',
        ):
            self.assertIn(required, source)

    def test_template_transport_is_shared_without_extra_token_side_effect(self):
        source = CLOUD.read_text(encoding="utf-8")
        start = source.index("async def send_template(")
        end = source.index("\n\nasync def marcar_leido", start)
        block = source[start:end]
        self.assertIn('"type": "template"', block)
        self.assertIn('"language": {"code": idioma}', block)
        self.assertNotIn("await revisar_token", block)

    def test_read_then_send_transforms_compose(self):
        source = TARGET.read_text(encoding="utf-8")
        after_read = read_transform(source)
        transformed = send_transform(after_read)
        self.assertNotIn("class CampanaCrearReq", transformed)
        self.assertNotIn("async def wa2_campana_crear", transformed)
        self.assertNotIn("async def _correr_campana", transformed)
        self.assertIn("whatsapp_campaigns_send_router", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_send_transform_is_idempotent_after_read_cut(self):
        once = send_transform(read_transform(TARGET.read_text(encoding="utf-8")))
        self.assertEqual(once, send_transform(once))


if __name__ == "__main__":
    unittest.main()
