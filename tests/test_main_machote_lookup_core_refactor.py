"""Dry-run guards for _machote_o_404's migration to core.database."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_machote_lookup_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("machote_lookup_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainMachoteLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_or_keeps_migrated_read(self):
        transformed = _load_transform()(self.source)
        delta = self.source.count("/rest/v1/machotes_contrato") - transformed.count("/rest/v1/machotes_contrato")
        self.assertIn(delta, (0, 1))
        compile(transformed, "main.py", "exec")

    def test_lookup_uses_core_and_preserves_404_contract(self):
        transformed = _load_transform()(self.source)
        start = transformed.index("async def _machote_o_404(")
        end = transformed.index("\n\nasync def _descargar_plantilla", start)
        block = transformed[start:end]

        self.assertIn('rows = await get_rows(\n            "machotes_contrato",', block)
        self.assertIn('"id": f"eq.{machote_id}"', block)
        self.assertIn('"user_id": f"eq.{user_id}"', block)
        self.assertIn('"select": select', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=15", block)
        self.assertIn("except httpx.HTTPStatusError:", block)
        self.assertEqual(block.count('raise HTTPException(status_code=404, detail="No encontramos ese machote.")'), 2)
        self.assertIn("if not rows:", block)
        self.assertIn("return rows[0]", block)
        self.assertNotIn("/rest/v1/machotes_contrato", block)
        self.assertNotIn("Authorization", block)
        self.assertNotIn("except Exception", block)


if __name__ == "__main__":
    unittest.main()
