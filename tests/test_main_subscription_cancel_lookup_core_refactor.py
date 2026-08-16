"""Guards for subscription_cancel's initial suscripciones lookup migration to Core."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_subscription_cancel_lookup_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("subscription_cancel_lookup_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainSubscriptionCancelLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_one_direct_subscriptions_read(self):
        transformed = _load_transform()(self.source)
        delta = self.source.count("/rest/v1/suscripciones") - transformed.count("/rest/v1/suscripciones")
        self.assertIn(delta, (0, 1))
        compile(transformed, "main.py", "exec")

    def test_cancel_lookup_preserves_http_empty_404_and_downstream_writes(self):
        transformed = _load_transform()(self.source)
        start = transformed.index('@app.post("/subscription/cancel")')
        end = transformed.index('@app.post("/subscription/revenuecat-webhook")', start)
        block = transformed[start:end]

        self.assertIn('subscription_rows = await get_rows(\n            "suscripciones",', block)
        self.assertIn('"user_id": f"eq.{user_id}"', block)
        self.assertIn('"select": "stripe_subscription_id,status"', block)
        self.assertIn('"order": "updated_at.desc"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=8", block)
        self.assertIn("except httpx.HTTPStatusError:\n        subscription_rows = []", block)
        self.assertIn("row = subscription_rows[0] if subscription_rows else {}", block)
        self.assertIn('raise HTTPException(status_code=404, detail="No se encontró suscripción activa.")', block)
        lookup_end = block.index("    subscription_id = row.get", block.index("subscription_rows = await get_rows"))
        lookup = block[:lookup_end]
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/suscripciones", lookup)
        # Stripe cancellation and Supabase status PATCH remain outside this read-only cut.
        self.assertIn('https://api.stripe.com/v1/subscriptions/{subscription_id}', block)
        self.assertIn('/rest/v1/suscripciones?user_id=eq.{user_id}', block)


if __name__ == "__main__":
    unittest.main()
