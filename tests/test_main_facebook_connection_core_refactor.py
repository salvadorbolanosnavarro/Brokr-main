"""Permanent guards for Facebook connection persistence delegated to Core."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
STORE = ROOT / "core" / "facebook_connection_store.py"
DISCONNECT = ROOT / "routers" / "facebook_disconnect.py"


def core_database_imports(source: str) -> set[str]:
    tree = ast.parse(source)
    return {
        alias.name
        for node in tree.body
        if isinstance(node, ast.ImportFrom) and node.module == "core.database"
        for alias in node.names
    }


class MainFacebookConnectionCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.store = STORE.read_text(encoding="utf-8")
        cls.disconnect = DISCONNECT.read_text(encoding="utf-8")

    def test_connection_persistence_delegates_to_core(self):
        source = self.source
        store = self.store
        disconnect = self.disconnect
        self.assertIn("post_rows", core_database_imports(source))
        self.assertIn('await post_rows(\n            "user_integrations",', source)
        self.assertIn("from routers.facebook_disconnect import router as facebook_disconnect_router", source)
        self.assertIn("app.include_router(facebook_disconnect_router)", source)
        self.assertIn('await delete_rows(\n            "user_integrations",', disconnect)
        self.assertIn('async def get_facebook_meta_row(user_id: str) -> dict:', store)
        self.assertIn('async def patch_facebook_meta(', store)
        self.assertIn('await get_rows(\n            "user_integrations",', store)
        self.assertIn('await post_rows(\n            "user_integrations",', store)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', store)
        self.assertIn('"provider": "eq.facebook"', store)
        self.assertIn('"provider": "facebook"', store)

    def test_connection_security_and_legacy_error_semantics_stay_intact(self):
        source = self.source
        store = self.store
        disconnect = self.disconnect
        self.assertIn('except httpx.HTTPStatusError:\n        # Historical behavior: Supabase HTTP rejections did not fail save-page.', source)
        self.assertIn('except httpx.HTTPStatusError:\n        return {}', store)
        self.assertIn('except httpx.HTTPStatusError:\n        pass', store)
        self.assertIn('user_id = await exigir_gestion_integraciones(request)', disconnect)
        self.assertIn('except httpx.HTTPStatusError:', disconnect)
        self.assertIn('"page_token": decrypt_facebook_secret(row.get("api_key", ""))', store)
        self.assertIn('meta["user_token"] = decrypt_facebook_secret(meta["user_token"])', store)
        self.assertIn('meta["user_token"] = encrypt_facebook_secret(meta["user_token"])', store)
        self.assertIn('"api_key": encrypt_facebook_secret(page_token)', store)
        self.assertNotIn('f"{SUPABASE_URL}/rest/v1/user_integrations",\n            headers={"apikey": SUPABASE_SERVICE_KEY', self._connection_slice(source))
        compile(source, "main.py", "exec")
        compile(store, "core/facebook_connection_store.py", "exec")
        compile(disconnect, "routers/facebook_disconnect.py", "exec")

    @staticmethod
    def _connection_slice(source: str) -> str:
        start = source.index('@app.post("/facebook/save-page")')
        end = source.index('@app.post("/facebook/publish-property")', start)
        return source[start:end]


if __name__ == "__main__":
    unittest.main()
