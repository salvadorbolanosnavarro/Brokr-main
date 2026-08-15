"""Permanent guards for subscription checkout's Core usuarios nombre read."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainCheckoutUserNameCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_main_compiles(self):
        compile(self.source, "main.py", "exec")

    def test_checkout_name_preserves_http_fallback_but_transport_propagation(self):
        start = self.source.index('@app.post("/subscription/checkout")')
        end = self.source.index("# ════════════════════════════════════════════════════════════════\n# BROQUER PARA EMPRESAS", start)
        block = self.source[start:end]

        self.assertIn('filas_nombre = await get_rows(\n            "usuarios",', block)
        self.assertIn('"select": "nombre"', block)
        self.assertIn("timeout=8", block)
        self.assertIn("except httpx.HTTPStatusError:\n        filas_nombre = []", block)
        self.assertIn('nombre = (filas_nombre[0] if filas_nombre else {}).get("nombre", email)', block)
        after_get = block.split('filas_nombre = await get_rows', 1)[1].split('nombre = (filas_nombre[0]', 1)[0]
        self.assertNotIn("except Exception:", after_get)
        self.assertNotIn("/rest/v1/usuarios", block)
        self.assertNotIn('"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"', after_get)


if __name__ == "__main__":
    unittest.main()
