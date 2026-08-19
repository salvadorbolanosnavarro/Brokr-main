"""Dry-run guard for Stripe webhook subscription POST Core routing."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCRIPT = ROOT / "scripts" / "refactor_main_stripe_webhook_subscription_post_core.py"
END_MARKER = '\n\n# ════════════════════════════════════════════════════════════════\n# Contactos / Importar desde EasyBroker'

spec = importlib.util.spec_from_file_location("stripe_webhook_subscription_post_transform", SCRIPT)
transform = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(transform)


class MainStripeWebhookSubscriptionPostTransformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.transformed = transform.transform_source(cls.source)

    def test_transform_is_exact_and_compiles(self):
        compile(self.transformed, "main.py", "exec")
        self.assertEqual(MAIN.read_text(encoding="utf-8"), self.source)
        start = self.transformed.index('@app.post("/subscription/webhook")')
        end = self.transformed.index(END_MARKER, start)
        block = self.transformed[start:end]
        self.assertEqual(block.count(transform.NEW), 1)
        self.assertNotIn(transform.OLD, block)
        source_end = self.source.index(END_MARKER, start)
        if transform.OLD in self.source[start:source_end]:
            self.assertEqual(self.transformed, self.source.replace(transform.OLD, transform.NEW, 1))
        else:
            self.assertEqual(self.transformed, self.source)

    def test_http_fail_soft_transport_contract_is_preserved(self):
        new = transform.NEW
        self.assertIn('await post_rows(', new)
        self.assertIn('"suscripciones"', new)
        self.assertIn('sb,', new)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', new)
        self.assertIn('timeout=10', new)
        self.assertIn('except httpx.HTTPStatusError:', new)
        self.assertIn('pass', new)
        self.assertNotIn('except Exception', new)
        self.assertNotIn('/rest/v1/suscripciones', new)


if __name__ == "__main__":
    unittest.main()
