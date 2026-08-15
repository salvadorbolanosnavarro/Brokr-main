"""Guards for the Lead Ads page-owner user_integrations reads."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_fb_page_owner_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("fb_page_owner_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainFacebookPageOwnerCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_two_direct_integrations_reads(self):
        transformed = _load_transform()(self.source)
        delta = self.source.count("/rest/v1/user_integrations") - transformed.count("/rest/v1/user_integrations")
        self.assertIn(delta, (0, 2))
        compile(transformed, "main.py", "exec")

    def test_page_owner_keeps_like_then_fallback_and_fail_soft_contract(self):
        transformed = _load_transform()(self.source)
        start = transformed.index("async def _fb_buscar_dueno_de_pagina(page_id: str) -> dict:")
        end = transformed.index("# Cómo se llaman los campos estándar de Meta", start)
        block = transformed[start:end]

        self.assertEqual(block.count('await get_rows(\n                "user_integrations",'), 2)
        self.assertIn('"meta": f"like.*{page_id}*"', block)
        self.assertIn('"limit": "20"', block)
        self.assertIn('"limit": "500"', block)
        self.assertEqual(block.count("except httpx.HTTPStatusError:\n                filas = []"), 1)
        self.assertIn("except httpx.HTTPStatusError:\n            filas = []", block)
        self.assertIn('except Exception as e:\n        _fb_log.error("Error buscando al dueño de la página %s: %s", page_id, e)\n        return {}', block)
        self.assertNotIn("/rest/v1/user_integrations", block)
        self.assertNotIn("headers=_sb_headers()", block)


if __name__ == "__main__":
    unittest.main()
