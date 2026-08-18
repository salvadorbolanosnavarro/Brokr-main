"""Permanent guards for subscription_activate's usuarios lookup through Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainSubscriptionActivateLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_main_compiles(self):
        compile(self.source, "main.py", "exec")

    def test_lookup_preserves_http_and_empty_404_contract(self):
        start = self.source.index('@app.post("/subscription/activate")')
        end = self.source.index('@app.post("/subscription/revenuecat-webhook")', start)
        block = self.source[start:end]
        self.assertIn('usuarios = await get_rows(\n            "usuarios",', block)
        self.assertIn('"stripe_customer_id": f"eq.{customer_id}"', block)
        self.assertIn('"select": "id,nombre,email"', block)
        self.assertIn("timeout=10", block)
        self.assertIn("except httpx.HTTPStatusError:\n        usuarios = []", block)
        self.assertIn("if not usuarios:", block)
        self.assertIn('raise HTTPException(status_code=404, detail=f"Usuario no encontrado para customer_id {customer_id}.")', block)
        lookup = block.split('user_id = usuario["id"]', 1)[0]
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/usuarios", lookup)


if __name__ == "__main__":
    unittest.main()
