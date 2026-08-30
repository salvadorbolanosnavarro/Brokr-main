"""Permanent architecture guard: main.py is a composition root, not a route monolith."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainCompositionRootTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_main_has_no_top_level_business_definitions(self) -> None:
        definitions = [
            node.name
            for node in self.tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        self.assertEqual([], definitions)

    def test_main_has_no_inline_app_routes(self) -> None:
        inline_routes: list[tuple[str, int]] = []
        for node in ast.walk(self.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                call = decorator if isinstance(decorator, ast.Call) else None
                target = call.func if call is not None else decorator
                if not isinstance(target, ast.Attribute):
                    continue
                if not isinstance(target.value, ast.Name) or target.value.id != "app":
                    continue
                if target.attr.lower() in {
                    "get", "post", "put", "patch", "delete", "options", "head", "trace", "api_route"
                }:
                    inline_routes.append((node.name, node.lineno))
        self.assertEqual([], inline_routes)

    def test_main_still_owns_application_composition(self) -> None:
        self.assertIn("app = FastAPI()", self.source)
        self.assertIn("app.include_router(", self.source)


if __name__ == "__main__":
    unittest.main()
