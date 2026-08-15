"""Permanent guards for the Lead Ads page-owner Core database contract."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainFacebookPageOwnerCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index("async def _fb_buscar_dueno_de_pagina(page_id: str) -> dict:")
        end = cls.source.index("# Cómo se llaman los campos estándar de Meta", start)
        cls.block = cls.source[start:end]

    def test_main_compiles(self):
        compile(self.source, "main.py", "exec")

    def test_page_owner_keeps_like_then_fallback_and_fail_soft_contract(self):
        block = self.block
        self.assertEqual(block.count("await get_rows("), 2)
        self.assertEqual(block.count('"user_integrations"'), 2)
        self.assertIn('"meta": f"like.*{page_id}*"', block)
        self.assertIn('"limit": "20"', block)
        self.assertIn('"limit": "500"', block)
        self.assertEqual(block.count("except httpx.HTTPStatusError:"), 2)
        self.assertEqual(block.count("filas = []"), 2)
        self.assertIn(
            'except Exception as e:\n        _fb_log.error("Error buscando al dueño de la página %s: %s", page_id, e)\n        return {}',
            block,
        )
        self.assertNotIn("/rest/v1/user_integrations", block)
        self.assertNotIn("headers=_sb_headers()", block)


if __name__ == "__main__":
    unittest.main()
