from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_cloud_api_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
ROUTER = ROOT / "routers" / "whatsapp_cloud_api.py"


class WhatsAppCloudApiExtractionTests(unittest.TestCase):
    def test_transport_contract_and_token_health(self):
        source = ROUTER.read_text(encoding="utf-8")
        for required in (
            "err.get(\"code\") not in (190, 102)",
            '"token_valido": False',
            '"ia_enabled": False',
            "WA_MAX_TEXTO = 4000",
            "preview_url\": False",
            "typing_indicator",
            "follow_redirects=True",
            "Este número no tiene un token de acceso válido.",
        ):
            self.assertIn(required, source)

    def test_transform_leaves_media_processing_and_callers(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertNotIn("async def _wa_send_text_detallado", transformed)
        self.assertNotIn("async def _descargar_media", transformed)
        self.assertIn("async def _transcribir_audio", transformed)
        self.assertIn("async def _describir_imagen", transformed)
        self.assertIn("async def _guardar_archivo", transformed)
        self.assertIn("from routers.whatsapp_cloud_api import", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
