"""Permanent guards for Facebook idempotency lookup delegated to Core."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "facebook_persistence.py"


class MainFbIdempotencyLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")
        start = cls.core.index("async def find_facebook_creation_by_idempotency(")
        end = cls.core.index("\n\nasync def reserve_facebook_creation(", start)
        cls.block = cls.core[start:end]

    def test_lookup_has_no_direct_supabase_rest(self):
        self.assertNotIn("/rest/v1/", self.block)
        self.assertNotIn("async def _fb_buscar_por_idempotencia(", self.source)
        self.assertIn("find_facebook_creation_by_idempotency as _fb_buscar_por_idempotencia", self.source)

    def test_core_lookup_preserves_fail_soft_contract(self):
        block = self.block
        self.assertIn('rows = await get_rows(', block)
        self.assertIn('FACEBOOK_AD_ENTITIES_TABLE,', block)
        self.assertIn('"user_id": f"eq.{user_id}"', block)
        self.assertIn('"idempotency_key": f"eq.{idempotency_key}"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=10", block)
        self.assertIn("except httpx.HTTPStatusError as exc:", block)
        self.assertIn("if facebook_table_missing(exc.response):", block)
        self.assertIn('warn_facebook_migration("buscar idempotencia", exc.response)', block)
        self.assertIn('except Exception as exc:', block)
        self.assertIn('_log.error("Error buscando idempotencia: %s", exc)', block)
        self.assertIn("if rows:\n            return rows[0]", block)
        self.assertTrue(block.rstrip().endswith("return {}"))
        self.assertNotIn("Authorization", block)
        compile(self.source, "main.py", "exec")
        compile(self.core, "core/facebook_persistence.py", "exec")


if __name__ == "__main__":
    unittest.main()
