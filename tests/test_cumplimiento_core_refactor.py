"""Dry-run Cumplimiento Core migration while protecting PLD business rules."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

from scripts.refactor_cumplimiento_core import transform

ROOT = Path(__file__).resolve().parents[1]
PROTECTED_FUNCTIONS = {
    "_config",
    "umbral_pesos",
    "evaluar_operacion",
    "fecha_limite",
    "construir_xml",
}


def _function_ast(source: str, name: str) -> str:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return ast.dump(node, include_attributes=False)
    raise AssertionError(f"Protected function not found: {name}")


class CumplimientoCoreRefactorTests(unittest.TestCase):
    def test_transform_migrates_only_infrastructure_and_compiles(self):
        source = (ROOT / "routers" / "cumplimiento.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn("from core.auth import require_user_id", updated)
        self.assertIn("from core.config import settings", updated)
        self.assertIn("from core.database import get_rows, patch_rows, post_rows", updated)
        self.assertIn("from core.storage import create_signed_object_url, upload_object", updated)
        self.assertNotIn("os.getenv", updated)
        self.assertNotIn("SUPABASE_SERVICE_KEY =", updated)
        self.assertNotIn("async def get_user_id_from_token", updated)
        self.assertNotIn("/storage/v1/object/", updated)
        self.assertIn("APP_URL = settings.app_url", updated)
        self.assertIn("await upload_object(", updated)
        self.assertIn("await create_signed_object_url(", updated)

        # Legal/business behavior is outside the scope of this refactor.
        for name in PROTECTED_FUNCTIONS:
            self.assertEqual(_function_ast(source, name), _function_ast(updated, name), name)
        self.assertIn('SCHEMA_VERSION = "1.0"', updated)
        self.assertIn('"valor_uma": 117.31, "umbral_aviso_uma": 8025', updated)
        self.assertIn('"meses_acumulacion": 6', updated)
        self.assertIn('"retencion_anios": 10, "dia_limite_aviso": 17', updated)
        compile(updated, "routers/cumplimiento.py", "exec")


if __name__ == "__main__":
    unittest.main()
