"""Dry-run and permanent guards for Facebook connection persistence in main.py."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_facebook_connection_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("fb_connection_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainFacebookConnectionCoreRefactorTests(unittest.TestCase):
    def test_transform_compiles_and_only_removes_five_direct_rest_calls(self):
        source = MAIN.read_text(encoding="utf-8")
        transform = _load_transform()
        transformed = transform(source)
        self.assertEqual(
            source.count("/rest/v1/user_integrations") - transformed.count("/rest/v1/user_integrations"),
            5,
        )
        compile(transformed, "main.py", "exec")

    def test_transformed_connection_persistence_uses_core_with_legacy_semantics(self):
        source = MAIN.read_text(encoding="utf-8")
        transformed = _load_transform()(source)
        self.assertIn('await post_rows(\n            "user_integrations",', transformed)
        self.assertIn('await get_rows(\n            "user_integrations",', transformed)
        self.assertIn('await delete_rows(\n            "user_integrations",', transformed)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', transformed)
        self.assertIn('except httpx.HTTPStatusError:\n        # Historical behavior: Supabase HTTP rejections did not fail save-page.', transformed)
        self.assertIn('except httpx.HTTPStatusError:\n        # Historical behavior: an HTTP rejection meant "no row"', transformed)
        self.assertIn('user_id = await exigir_gestion_integraciones(request)', transformed)
        self.assertIn('"provider": "eq.facebook"', transformed)
        self.assertIn('"provider": "facebook"', transformed)
        self.assertIn('"page_token": descifrar_secreto(row.get("api_key", ""))', transformed)
        self.assertIn('meta["user_token"] = cifrar_secreto(meta["user_token"])', transformed)


if __name__ == "__main__":
    unittest.main()
