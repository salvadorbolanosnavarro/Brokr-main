"""Guards for /profile/status integration reads delegated to Core."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_profile_status_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("profile_status_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainProfileStatusCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_removes_at_most_the_profile_status_direct_rest_read(self):
        transformed = _load_transform()(self.source)
        delta = self.source.count("/rest/v1/user_integrations") - transformed.count("/rest/v1/user_integrations")
        self.assertIn(delta, (0, 1))
        compile(transformed, "main.py", "exec")

    def test_transformed_profile_status_uses_core_and_keeps_fail_soft_contract(self):
        transformed = _load_transform()(self.source)
        start = transformed.index('@app.get("/profile/status")')
        end = transformed.index("# ────────────────────────────────────────────\n# GROQ CHAT PROXY", start)
        block = transformed[start:end]
        integrations_end = block.index("    # Parsear cada provider")
        integrations_block = block[:integrations_end]

        self.assertIn('rows = await get_rows(\n            "user_integrations",', integrations_block)
        self.assertIn('"provider": "in.(easybroker,facebook)"', integrations_block)
        self.assertIn('"select": "provider,api_key,meta"', integrations_block)
        self.assertIn("timeout=8", integrations_block)
        self.assertIn('except Exception:\n        return {"eb": {"configured": False, "masked": ""}, "fb": {"connected": False}}', integrations_block)
        self.assertNotIn("/rest/v1/user_integrations", integrations_block)
        self.assertNotIn('"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"', integrations_block)


if __name__ == "__main__":
    unittest.main()
