"""Dry-run the exact Firmas entitlement migration against current source."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_firmas_entitlement import transform


ROOT = Path(__file__).resolve().parents[1]


class FirmasEntitlementRefactorTests(unittest.TestCase):
    def test_transform_matches_current_source_and_compiles(self):
        source = (ROOT / "routers" / "firmas.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn(
            "from core.subscriptions import require_paid_feature_access",
            updated,
        )
        self.assertNotIn("Falla ABIERTO", updated)
        self.assertNotIn("async def _suscripcion_activa", updated)
        self.assertIn("async def _uid_max", updated)
        self.assertIn("return await require_paid_feature_access(", updated)
        compile(updated, "routers/firmas.py", "exec")


if __name__ == "__main__":
    unittest.main()
