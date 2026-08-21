from pathlib import Path
import unittest

from scripts.refactor_whatsapp_extract_stats_api_core import transform_source

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
ROUTER = ROOT / "routers" / "whatsapp_stats_api.py"


class WhatsAppStatsApiExtractionTests(unittest.TestCase):
    def test_stats_router_preserves_pagination_and_secret_stripping(self):
        source = ROUTER.read_text(encoding="utf-8")
        for required in (
            '@router.get("/estadisticas")',
            "paralelo: int = 6",
            "pagina = 1000",
            "bloque < 40",
            "tope=20000",
            '"select": "conversacion_id,direction,sender,created_at"',
            'n.pop("access_token", None)',
            '"numeros_conectados": len(numeros)',
            "_agrega_ventana",
        ):
            self.assertIn(required, source)

    def test_transform_removes_only_stats_io(self):
        transformed = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertNotIn("async def _sb_diag", transformed)
        self.assertNotIn("async def _sb_get_paginado", transformed)
        self.assertNotIn("async def wa2_estadisticas", transformed)
        self.assertIn("whatsapp_stats_api_router", transformed)
        compile(transformed, "whatsapp.py", "exec")

    def test_transform_is_idempotent(self):
        once = transform_source(TARGET.read_text(encoding="utf-8"))
        self.assertEqual(once, transform_source(once))


if __name__ == "__main__":
    unittest.main()
