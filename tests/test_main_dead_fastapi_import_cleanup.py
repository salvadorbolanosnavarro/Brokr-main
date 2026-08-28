"""Prepared/certified guards for the post-route FastAPI import cleanup."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
DEAD_NAMES = {
    "Query",
    "Request",
    "UploadFile",
    "File",
    "BackgroundTasks",
    "Response",
}
REQUIRED_NAMES = {"FastAPI", "HTTPException"}


class MainDeadFastAPIImportCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)
        cls.loads = {
            node.id
            for node in ast.walk(cls.tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        cls.fastapi_imports = [
            node
            for node in cls.tree.body
            if isinstance(node, ast.ImportFrom) and node.module == "fastapi" and node.level == 0
        ]

    def test_cleanup_targets_are_semantically_dead(self):
        self.assertEqual(set(), DEAD_NAMES & self.loads)

    def test_fastapi_import_has_only_prepared_or_certified_shape(self):
        self.assertEqual(1, len(self.fastapi_imports))
        names = {alias.asname or alias.name for alias in self.fastapi_imports[0].names}
        self.assertTrue(REQUIRED_NAMES <= names)
        self.assertIn(names, (REQUIRED_NAMES, REQUIRED_NAMES | DEAD_NAMES))

    def test_main_compiles(self):
        compile(self.source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
