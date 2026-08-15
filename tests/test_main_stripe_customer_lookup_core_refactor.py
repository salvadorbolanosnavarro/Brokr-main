"""Permanent guards for Stripe customer usuarios lookup through Core."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainStripeCustomerLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_main_compiles(self):
        compile(self.source, "main.py", "exec")

    def test_lookup_preserves_http_empty_but_transport_propagation(self):
        start = self.source.index("async def _get_or_create_stripe_customer(user_id: str, email: str, nombre: str) -> str:")
        end = self.source.index('@app.post("/subscription/checkout")', start)
        block = self.source[start:end]

        self.assertIn('rows = await get_rows(\n            "usuarios",', block)
        self.assertIn('"select": "stripe_customer_id,nombre"', block)
        self.assertIn("timeout=10", block)
        self.assertIn("except httpx.HTTPStatusError:\n        rows = []", block)
        self.assertIn("row = rows[0] if rows else {}", block)
        lookup = block.split("# 2. Crear Customer en Stripe", 1)[0]
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/usuarios", lookup)
        # The later PATCH is deliberately outside this read-only cut.
        self.assertIn("/rest/v1/usuarios?id=eq.{user_id}", block)


if __name__ == "__main__":
    unittest.main()
