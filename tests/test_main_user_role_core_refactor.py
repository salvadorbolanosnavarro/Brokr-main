"""Guards for get_user_rol's migration to core.database."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_user_role_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("user_role_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainUserRoleCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_one_direct_usuarios_read(self):
        transformed = _load_transform()(self.source)
        delta = self.source.count("/rest/v1/usuarios") - transformed.count("/rest/v1/usuarios")
        self.assertIn(delta, (0, 1))
        compile(transformed, "main.py", "exec")

    def test_role_keeps_fail_soft_agente_contract(self):
        transformed = _load_transform()(self.source)
        start = transformed.index("async def get_user_rol(user_id: str) -> str:")
        end = transformed.index("# Helper: obtiene rol + activo", start)
        block = transformed[start:end]

        self.assertIn('rows = await get_rows(\n            "usuarios",', block)
        self.assertIn('"select": "rol"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=8", block)
        self.assertIn('return rows[0].get("rol") or "agente"', block)
        self.assertIn('except Exception:\n        pass\n    return "agente"', block)
        self.assertNotIn("/rest/v1/usuarios", block)
        self.assertNotIn('"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"', block)


if __name__ == "__main__":
    unittest.main()
