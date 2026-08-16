"""Dry-run guards for GET /contrato/machotes migration to core.database."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_machotes_list_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("machotes_list_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainMachotesListCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_or_keeps_migrated_read(self):
        transformed = _load_transform()(self.source)
        start = transformed.index('@app.get("/contrato/machotes")')
        end = transformed.index('@app.get("/contrato/machote/{machote_id}")', start)
        block = transformed[start:end]
        self.assertNotIn("/rest/v1/machotes_contrato", block)
        compile(transformed, "main.py", "exec")

    def test_list_uses_core_and_preserves_http_500_contract(self):
        transformed = _load_transform()(self.source)
        start = transformed.index('@app.get("/contrato/machotes")')
        end = transformed.index('@app.get("/contrato/machote/{machote_id}")', start)
        block = transformed[start:end]

        self.assertIn('rows = await get_rows(\n            "machotes_contrato",', block)
        self.assertIn('"user_id": f"eq.{user_id}"', block)
        self.assertIn('"select": "id,titulo,tipo,campos,motor,created_at"', block)
        self.assertIn('"order": "created_at.desc"', block)
        self.assertIn("timeout=15", block)
        self.assertIn("except httpx.HTTPStatusError:", block)
        self.assertIn('raise HTTPException(status_code=500, detail="No se pudieron cargar tus machotes.")', block)
        self.assertIn('return {"machotes": rows}', block)
        self.assertNotIn("Authorization", block)
        self.assertNotIn("except Exception", block)


if __name__ == "__main__":
    unittest.main()
