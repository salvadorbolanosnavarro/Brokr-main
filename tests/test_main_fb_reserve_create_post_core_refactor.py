"""Permanent guard for Facebook creation reservation delegated to Core."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "facebook_persistence.py"


class MainFbReserveCreatePostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")
        start = cls.core.index("async def reserve_facebook_creation(")
        end = cls.core.index("\n\nasync def update_facebook_entity(", start)
        cls.block = cls.core[start:end]

    def test_reserve_post_uses_core_with_exact_legacy_success_statuses(self):
        block = self.block
        self.assertIn('rows = await post_rows(', block)
        self.assertIn('FACEBOOK_AD_ENTITIES_TABLE,', block)
        self.assertIn('row,', block)
        self.assertIn('prefer="return=representation"', block)
        self.assertIn('timeout=10', block)
        self.assertIn('accepted_statuses=(200, 201)', block)
        self.assertNotIn('/rest/v1/', block)
        self.assertIn('return {"modo": "nuevo", "row_id": (rows[0]["id"] if rows else row["id"])}', block)
        self.assertNotIn("async def _fb_reservar_creacion(", self.source)
        self.assertIn("reserve_facebook_creation as _fb_reservar_creacion", self.source)

    def test_idempotency_table_missing_and_fail_soft_contract_are_preserved(self):
        block = self.block
        self.assertIn('except httpx.HTTPStatusError as exc:', block)
        self.assertIn('response = exc.response', block)
        self.assertIn('if facebook_table_missing(response):', block)
        self.assertIn('warn_facebook_migration("reservar creación", response)', block)
        self.assertIn('if response.status_code == 409 and idempotency_key:', block)
        self.assertIn('previous = await find_facebook_creation_by_idempotency(user_id, idempotency_key)', block)
        self.assertIn('return {"modo": "duplicado", "row": previous}', block)
        self.assertIn('"No se pudo registrar la creación en %s: %s %s"', block)
        self.assertIn('except Exception as exc:', block)
        self.assertIn('"Error registrando la creación en %s: %s"', block)
        self.assertTrue(block.rstrip().endswith('return {"modo": "sin_tabla"}'))
        compile(self.source, "main.py", "exec")
        compile(self.core, "core/facebook_persistence.py", "exec")


if __name__ == "__main__":
    unittest.main()
