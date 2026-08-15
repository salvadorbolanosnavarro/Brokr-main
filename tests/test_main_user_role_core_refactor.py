"""Permanent guards for get_user_rol's Core database contract."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainUserRoleCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_main_compiles(self):
        compile(self.source, "main.py", "exec")

    def test_role_keeps_fail_soft_agente_contract_and_uses_core(self):
        start = self.source.index("async def get_user_rol(user_id: str) -> str:")
        end = self.source.index("# Helper: obtiene rol + activo", start)
        block = self.source[start:end]

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
