"""Guards for _get_fb_meta's migration to core.database."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_fb_meta_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("fb_meta_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainFacebookMetaCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_only_one_direct_integrations_read(self):
        transformed = _load_transform()(self.source)
        delta = self.source.count("/rest/v1/user_integrations") - transformed.count("/rest/v1/user_integrations")
        self.assertIn(delta, (0, 1))
        compile(transformed, "main.py", "exec")

    def test_fb_meta_preserves_http_and_transport_error_contract(self):
        transformed = _load_transform()(self.source)
        start = transformed.index("async def _get_fb_meta(user_id: str) -> dict:")
        end = transformed.index('@app.post("/facebook/ad-description")', start)
        block = transformed[start:end]

        self.assertIn('rows = await get_rows(\n            "user_integrations",', block)
        self.assertIn('"provider": "eq.facebook"', block)
        self.assertIn('"select": "meta"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=10", block)
        self.assertIn("except httpx.HTTPStatusError:", block)
        self.assertIn('raise HTTPException(status_code=400, detail="Facebook no conectado")', block)
        self.assertIn("if not rows:", block)
        self.assertIn('meta_raw = rows[0].get("meta", "{}")', block)
        self.assertNotIn("except Exception:", block.split('meta_raw = rows[0].get("meta", "{}")', 1)[0])
        self.assertNotIn("/rest/v1/user_integrations", block)
        self.assertNotIn('"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"', block)


if __name__ == "__main__":
    unittest.main()
