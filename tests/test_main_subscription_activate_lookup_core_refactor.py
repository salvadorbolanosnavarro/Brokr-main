"""Permanent guards for subscription_activate's usuarios lookup through Core."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
ROUTER = ROOT / "routers" / "subscription_activate.py"
MAIN = ROOT / "main.py"


class MainSubscriptionActivateLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ROUTER.read_text(encoding="utf-8")
        cls.main = MAIN.read_text(encoding="utf-8")

    def test_files_compile(self):
        compile(self.source, "routers/subscription_activate.py", "exec")
        compile(self.main, "main.py", "exec")

    def test_lookup_preserves_http_and_empty_404_contract(self):
        block = self.source
        self.assertIn('users = await get_rows(\n            "usuarios",', block)
        self.assertIn('"stripe_customer_id": f"eq.{customer_id}"', block)
        self.assertIn('"select": "id,nombre,email"', block)
        self.assertIn("timeout=10", block)
        self.assertIn("except httpx.HTTPStatusError:\n        users = []", block)
        self.assertIn("if not users:", block)
        self.assertIn('raise HTTPException(status_code=404, detail=f"Usuario no encontrado para customer_id {customer_id}.")', block)
        lookup = block.split('user = users[0]', 1)[0]
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/usuarios", lookup)
        self.assertNotIn('@app.post("/subscription/activate")', self.main)


if __name__ == "__main__":
    unittest.main()
