"""Permanent guard for _fb_reservar_creacion POST Core routing."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainFbReserveCreatePostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index("async def _fb_reservar_creacion(")
        end = cls.source.index("\n\nasync def _fb_buscar_por_idempotencia", start)
        cls.block = cls.source[start:end]

    def test_reserve_post_uses_core_with_exact_legacy_success_statuses(self):
        block = self.block
        self.assertIn('filas = await post_rows(\n                _FB_TABLA_ENTIDADES,', block)
        self.assertIn('fila,', block)
        self.assertIn('prefer="return=representation"', block)
        self.assertIn('timeout=10', block)
        self.assertIn('accepted_statuses=(200, 201)', block)
        self.assertNotIn('f"{SUPABASE_URL}/rest/v1/{_FB_TABLA_ENTIDADES}"', block)
        self.assertIn('return {"modo": "nuevo", "row_id": (filas[0]["id"] if filas else fila["id"])}', block)

    def test_idempotency_table_missing_and_fail_soft_contract_are_preserved(self):
        block = self.block
        self.assertIn('except httpx.HTTPStatusError as e:', block)
        self.assertIn('r = e.response', block)
        self.assertIn('if _fb_tabla_falta(r):', block)
        self.assertIn('_fb_avisa_migracion("reservar creación", r)', block)
        self.assertIn('if r.status_code == 409 and idempotency_key:', block)
        self.assertIn('previa = await _fb_buscar_por_idempotencia(user_id, idempotency_key)', block)
        self.assertIn('return {"modo": "duplicado", "row": previa}', block)
        self.assertIn('_fb_log.error("No se pudo registrar la creación en %s: %s %s",', block)
        self.assertIn('except Exception as e:', block)
        self.assertIn('_fb_log.error("Error registrando la creación en %s: %s", _FB_TABLA_ENTIDADES, e)', block)
        self.assertTrue(block.rstrip().endswith('return {"modo": "sin_tabla"}'))


if __name__ == "__main__":
    unittest.main()
