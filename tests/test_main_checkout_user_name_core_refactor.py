"""Guards for subscription checkout's usuarios nombre read migration to Core."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_checkout_user_name_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("checkout_name_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainCheckoutUserNameCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_one_direct_usuarios_read(self):
        transformed = _load_transform()(self.source)
        delta = self.source.count("/rest/v1/usuarios") - transformed.count("/rest/v1/usuarios")
        self.assertIn(delta, (0, 1))
        compile(transformed, "main.py", "exec")

    def test_checkout_name_preserves_http_fallback_but_transport_propagation(self):
        transformed = _load_transform()(self.source)
        start = transformed.index('@app.post("/subscription/checkout")')
        end = transformed.index('@app.post("/subscription/portal")', start)
        block = transformed[start:end]

        self.assertIn('filas_nombre = await get_rows(\n            "usuarios",', block)
        self.assertIn('"select": "nombre"', block)
        self.assertIn("timeout=8", block)
        self.assertIn("except httpx.HTTPStatusError:\n        filas_nombre = []", block)
        self.assertIn('nombre = (filas_nombre[0] if filas_nombre else {}).get("nombre", email)', block)
        self.assertNotIn("except Exception:", block.split('nombre = (filas_nombre[0]', 1)[0].split('filas_nombre = await get_rows', 1)[1])
        self.assertNotIn("/rest/v1/usuarios", block)


if __name__ == "__main__":
    unittest.main()
