"""Permanent guards for get_user_rol's Core database contract."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "user_access.py"
MAIN = ROOT / "main.py"


class MainUserRoleCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CORE.read_text(encoding="utf-8")
        cls.main = MAIN.read_text(encoding="utf-8")

    def test_main_and_core_compile(self):
        compile(self.source, "core/user_access.py", "exec")
        compile(self.main, "main.py", "exec")

    def test_role_keeps_fail_soft_agente_contract_and_uses_core(self):
        start = self.source.index("async def get_user_rol(user_id: str) -> str:")
        end = self.source.index("async def get_user_access_state", start)
        block = self.source[start:end]

        self.assertIn('rows = await get_rows(\n            "usuarios",', block)
        self.assertIn('"select": "rol"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=8", block)
        self.assertIn('return rows[0].get("rol") or "agente"', block)
        self.assertIn('except Exception:\n        pass\n    return "agente"', block)
        self.assertNotIn("/rest/v1/usuarios", block)
        self.assertIn("from core.database import get_rows", self.source)
        self.assertIn(
            "from core.user_access import get_user_access_state, get_user_rol",
            self.main,
        )
        self.assertNotIn("async def get_user_rol(", self.main)


if __name__ == "__main__":
    unittest.main()
