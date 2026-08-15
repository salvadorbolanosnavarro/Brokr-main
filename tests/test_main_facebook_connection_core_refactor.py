"""Permanent guards for Facebook connection persistence delegated to Core."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainFacebookConnectionCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_connection_persistence_delegates_to_core(self):
        source = self.source
        self.assertIn("from core.database import delete_rows, get_rows, post_rows", source)
        self.assertIn('await post_rows(\n            "user_integrations",', source)
        self.assertIn('await get_rows(\n            "user_integrations",', source)
        self.assertIn('await delete_rows(\n            "user_integrations",', source)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', source)
        self.assertIn('"provider": "eq.facebook"', source)
        self.assertIn('"provider": "facebook"', source)

    def test_connection_security_and_legacy_error_semantics_stay_intact(self):
        source = self.source
        self.assertIn('except httpx.HTTPStatusError:\n        # Historical behavior: Supabase HTTP rejections did not fail save-page.', source)
        self.assertIn('except httpx.HTTPStatusError:\n        # Historical behavior: an HTTP rejection meant "no row"', source)
        self.assertIn('user_id = await exigir_gestion_integraciones(request)', source)
        self.assertIn('"page_token": descifrar_secreto(row.get("api_key", ""))', source)
        self.assertIn('meta["user_token"] = cifrar_secreto(meta["user_token"])', source)
        self.assertNotIn('f"{SUPABASE_URL}/rest/v1/user_integrations",\n            headers={"apikey": SUPABASE_SERVICE_KEY', self._connection_slice(source))
        compile(source, "main.py", "exec")

    @staticmethod
    def _connection_slice(source: str) -> str:
        start = source.index('@app.post("/facebook/save-page")')
        end = source.index('@app.post("/facebook/publish-property")', start)
        return source[start:end]


if __name__ == "__main__":
    unittest.main()
