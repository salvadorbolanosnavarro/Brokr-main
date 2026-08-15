"""Guards for Stripe customer usuarios lookup migration to Core."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_stripe_customer_lookup_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("stripe_customer_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainStripeCustomerLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_one_direct_usuarios_read(self):
        transformed = _load_transform()(self.source)
        delta = self.source.count("/rest/v1/usuarios") - transformed.count("/rest/v1/usuarios")
        self.assertIn(delta, (0, 1))
        compile(transformed, "main.py", "exec")

    def test_lookup_preserves_http_empty_but_transport_propagation(self):
        transformed = _load_transform()(self.source)
        start = transformed.index("async def _get_or_create_stripe_customer(user_id: str, email: str, nombre: str) -> str:")
        end = transformed.index('@app.post("/subscription/checkout")', start)
        block = transformed[start:end]

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
