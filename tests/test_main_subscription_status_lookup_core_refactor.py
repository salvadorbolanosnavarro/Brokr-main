"""Guards for subscription_status' suscripciones lookup migration to Core."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_subscription_status_lookup_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("subscription_status_lookup_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainSubscriptionStatusLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_one_direct_subscriptions_read(self):
        transformed = _load_transform()(self.source)
        delta = self.source.count("/rest/v1/suscripciones") - transformed.count("/rest/v1/suscripciones")
        self.assertIn(delta, (0, 1))
        compile(transformed, "main.py", "exec")

    def test_status_lookup_preserves_http_and_empty_fallback_contract(self):
        transformed = _load_transform()(self.source)
        start = transformed.index('@app.get("/subscription/status")')
        end = transformed.index('# ════════════════════════════════════════════════════════════════\n# Trial de Broquer Max SIN tarjeta', start)
        block = transformed[start:end]

        self.assertIn('subscription_rows = await get_rows(\n            "suscripciones",', block)
        self.assertIn('"org_id": f"eq.{_oid}"', block)
        self.assertIn('"select": "*"', block)
        self.assertIn('"order": "updated_at.desc"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=8", block)
        self.assertIn("except httpx.HTTPStatusError:\n        subscription_rows = []", block)
        self.assertIn("if not subscription_rows:", block)
        self.assertIn('"status": "sin_suscripcion"', block)
        self.assertIn("row = subscription_rows[0]", block)
        lookup_start = block.index("    _oid = await get_org_id_for_user(user_id)")
        lookup_end = block.index("    row = subscription_rows[0]", lookup_start)
        lookup = block[lookup_start:lookup_end]
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/suscripciones", lookup)
        # Trial expiration behavior stays outside this bounded read migration.
        self.assertIn("asyncio.create_task(_expirar_trial_suscripcion", block)


if __name__ == "__main__":
    unittest.main()
