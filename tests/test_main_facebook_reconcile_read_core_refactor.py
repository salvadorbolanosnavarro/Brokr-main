"""Permanent guards for /facebook/reconcile entity-ledger Core read."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_reconcile.py"


class MainFacebookReconcileReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.block = ROUTER.read_text(encoding="utf-8")

    def test_direct_entity_get_stays_removed(self):
        self.assertNotIn(
            'r = await client.get(\n            f"{SUPABASE_URL}/rest/v1/{_FB_TABLA_ENTIDADES}"',
            self.block,
        )
        self.assertNotIn("async def facebook_reconcile(", self.source)
        self.assertIn("from routers.facebook_reconcile import router as facebook_reconcile_router", self.source)

    def test_core_read_preserves_missing_table_and_reconcile_logic(self):
        block = self.block
        self.assertIn('filas = await get_rows(', block)
        self.assertIn('FACEBOOK_AD_ENTITIES_TABLE,', block)
        self.assertIn(
            '{"user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "200"}',
            block,
        )
        self.assertIn('timeout=15', block)
        self.assertIn('except httpx.HTTPStatusError as exc:', block)
        self.assertIn('if facebook_table_missing(exc.response):', block)
        self.assertIn('warn_facebook_migration("reconciliar", exc.response)', block)
        self.assertIn('status_code=503', block)
        self.assertIn(
            'raise HTTPException(status_code=502, detail="No se pudo leer el registro de campañas.")',
            block,
        )
        self.assertIn('await update_facebook_entity(', block)
        self.assertIn('elif limpiar:', block)
        self.assertIn('"DELETE",', block)
        compile(self.source, "main.py", "exec")
        compile(self.block, "routers/facebook_reconcile.py", "exec")


if __name__ == "__main__":
    unittest.main()
