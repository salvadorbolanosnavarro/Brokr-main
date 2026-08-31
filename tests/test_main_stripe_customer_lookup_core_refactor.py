"""Permanent guards for Stripe customer usuarios lookup through Core."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "stripe.py"


class MainStripeCustomerLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.source = CORE.read_text(encoding="utf-8")

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.source, "core/stripe.py", "exec")

    def test_lookup_preserves_http_empty_but_transport_propagation(self):
        block = self.source
        self.assertIn('async def get_or_create_stripe_customer(', block)
        self.assertIn('rows = await get_rows(\n            "usuarios",', block)
        self.assertIn('"select": "stripe_customer_id,nombre"', block)
        self.assertIn("timeout=10", block)
        self.assertIn("except httpx.HTTPStatusError:\n        rows = []", block)
        self.assertIn("row = rows[0] if rows else {}", block)
        lookup = block.split("async with httpx.AsyncClient(timeout=10)", 1)[0]
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/usuarios", lookup)
        self.assertIn('await patch_rows(\n            "usuarios",', block)
        self.assertNotIn("/rest/v1/usuarios?id=eq.{user_id}", block)
        self.assertNotIn('async def _get_or_create_stripe_customer', self.main)


if __name__ == "__main__":
    unittest.main()
