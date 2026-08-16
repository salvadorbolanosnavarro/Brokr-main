"""Guards for subscription_activate's usuarios lookup migration to Core."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_subscription_activate_lookup_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("subscription_activate_lookup_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainSubscriptionActivateLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_one_direct_usuarios_read(self):
        transformed = _load_transform()(self.source)
        delta = self.source.count("/rest/v1/usuarios") - transformed.count("/rest/v1/usuarios")
        self.assertIn(delta, (0, 1))
        compile(transformed, "main.py", "exec")

    def test_lookup_preserves_http_and_empty_404_contract(self):
        transformed = _load_transform()(self.source)
        start = transformed.index('@app.post("/subscription/activate")')
        end = transformed.index('@app.get("/subscription/status")', start)
        block = transformed[start:end]

        self.assertIn('usuarios = await get_rows(\n            "usuarios",', block)
        self.assertIn('"stripe_customer_id": f"eq.{customer_id}"', block)
        self.assertIn('"select": "id,nombre,email"', block)
        self.assertIn("timeout=10", block)
        self.assertIn("except httpx.HTTPStatusError:\n        usuarios = []", block)
        self.assertIn("if not usuarios:", block)
        self.assertIn('raise HTTPException(status_code=404, detail=f"Usuario no encontrado para customer_id {customer_id}.")', block)
        self.assertIn("usuario = usuarios[0]", block)
        lookup = block.split("user_id = usuario[\"id\"]", 1)[0]
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/usuarios", lookup)
        # Activating the subscription remains outside this read-only cut.
        self.assertIn("/rest/v1/suscripciones", block)


if __name__ == "__main__":
    unittest.main()
