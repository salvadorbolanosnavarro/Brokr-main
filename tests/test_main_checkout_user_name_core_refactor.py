"""Permanent guards for subscription checkout's Core usuarios nombre read."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "subscription_checkout.py"


class MainCheckoutUserNameCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.source = ROUTER.read_text(encoding="utf-8")

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.source, "routers/subscription_checkout.py", "exec")

    def test_checkout_name_preserves_http_fallback_but_transport_propagation(self):
        block = self.source
        self.assertIn('filas_nombre = await get_rows(\n            "usuarios",', block)
        self.assertIn('"select": "nombre"', block)
        self.assertIn("timeout=8", block)
        self.assertIn("except httpx.HTTPStatusError:\n        filas_nombre = []", block)
        self.assertIn('nombre = (filas_nombre[0] if filas_nombre else {}).get("nombre", email)', block)
        after_get = block.split('filas_nombre = await get_rows', 1)[1].split('nombre = (filas_nombre[0]', 1)[0]
        self.assertNotIn("except Exception:", after_get)
        self.assertNotIn("/rest/v1/usuarios", block)
        self.assertNotIn('SUPABASE_SERVICE_KEY', after_get)
        self.assertNotIn('@app.post("/subscription/checkout")', self.main)


if __name__ == "__main__":
    unittest.main()
