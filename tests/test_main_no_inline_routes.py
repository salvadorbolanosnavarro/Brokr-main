"""Architecture ratchet: main.py is wiring only, never an HTTP route owner."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
HTTP_DECORATORS = {
    "get", "post", "put", "patch", "delete", "options", "head", "trace", "websocket", "api_route"
}


class MainNoInlineRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.tree = ast.parse(cls.source)

    def test_main_has_no_app_owned_http_decorators(self):
        offenders: list[tuple[str, int, str]] = []
        for node in ast.walk(self.tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                call = decorator if isinstance(decorator, ast.Call) else None
                target = call.func if call else decorator
                if not (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "app"
                    and target.attr in HTTP_DECORATORS
                ):
                    continue
                route = "<dynamic>"
                if call and call.args and isinstance(call.args[0], ast.Constant):
                    route = str(call.args[0].value)
                offenders.append((node.name, decorator.lineno, route))
        self.assertEqual([], offenders, f"main.py regained inline HTTP routes: {offenders}")

    def test_main_still_owns_fastapi_bootstrap(self):
        app_assignments = [
            node
            for node in self.tree.body
            if isinstance(node, ast.Assign)
            and any(isinstance(target, ast.Name) and target.id == "app" for target in node.targets)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id == "FastAPI"
        ]
        self.assertEqual(1, len(app_assignments))
        self.assertIn("app.include_router(", self.source)


if __name__ == "__main__":
    unittest.main()
