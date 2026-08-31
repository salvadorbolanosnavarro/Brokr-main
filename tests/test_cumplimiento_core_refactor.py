"""Permanent regression guard for migrated Cumplimiento infrastructure."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class CumplimientoCoreRegressionTests(unittest.TestCase):
    def test_router_uses_core_without_changing_pld_contract_markers(self):
        source = (ROOT / "routers" / "cumplimiento.py").read_text(encoding="utf-8")

        self.assertIn("from core.auth import require_user_id", source)
        self.assertIn("from core.config import settings", source)
        self.assertIn("from core.database import get_rows, patch_rows, post_rows", source)
        self.assertIn("from core.storage import create_signed_object_url, upload_object", source)
        self.assertNotIn("os.getenv", source)
        self.assertNotIn("SUPABASE_SERVICE_KEY =", source)
        self.assertNotIn("async def get_user_id_from_token", source)
        self.assertNotIn("/storage/v1/object/", source)
        self.assertIn("APP_URL = settings.app_url", source)
        self.assertIn("await upload_object(", source)
        self.assertIn("await create_signed_object_url(", source)

        # Legal/business rules remain explicit invariants of this router.
        self.assertIn('SCHEMA_VERSION = "1.0"', source)
        self.assertIn('"valor_uma": 117.31, "umbral_aviso_uma": 8025', source)
        self.assertIn('"umbral_identifica_uma": 8025, "meses_acumulacion": 6', source)
        self.assertIn('"retencion_anios": 10, "dia_limite_aviso": 17', source)
        self.assertIn("def umbral_pesos(", source)
        self.assertIn("async def evaluar_operacion(", source)
        self.assertIn("def fecha_limite(", source)
        self.assertIn("def construir_xml(", source)
        compile(source, "routers/cumplimiento.py", "exec")


if __name__ == "__main__":
    unittest.main()
