"""Permanent guards for _fb_buscar_por_idempotencia Core delegation."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainFbIdempotencyLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index("async def _fb_buscar_por_idempotencia(")
        end = cls.source.index("\n\nasync def _fb_actualizar_entidad(", start)
        cls.block = cls.source[start:end]

    def test_lookup_has_no_direct_supabase_rest(self):
        self.assertNotIn("/rest/v1/", self.block)

    def test_core_lookup_preserves_fail_soft_contract(self):
        block = self.block
        self.assertIn('filas = await get_rows(\n                _FB_TABLA_ENTIDADES,', block)
        self.assertIn('"user_id": f"eq.{user_id}"', block)
        self.assertIn('"idempotency_key": f"eq.{idempotency_key}"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=10", block)
        self.assertIn("except httpx.HTTPStatusError as e:", block)
        self.assertIn("if _fb_tabla_falta(e.response):", block)
        self.assertIn('_fb_avisa_migracion("buscar idempotencia", e.response)', block)
        self.assertIn('except Exception as e:\n        _fb_log.error("Error buscando idempotencia: %s", e)', block)
        self.assertIn("if filas:\n            return filas[0]", block)
        self.assertTrue(block.rstrip().endswith("return {}"))
        self.assertNotIn("Authorization", block)
        self.assertNotIn("_sb_headers", block)


if __name__ == "__main__":
    unittest.main()
