"""Permanent guards for get_user_access_state's Core database contract."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "user_access.py"
MAIN = ROOT / "main.py"


class MainUserAccessStateCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CORE.read_text(encoding="utf-8")
        cls.main = MAIN.read_text(encoding="utf-8")

    def test_main_and_core_compile(self):
        compile(self.source, "core/user_access.py", "exec")
        compile(self.main, "main.py", "exec")

    def test_access_state_keeps_fail_soft_defaults_and_uses_core(self):
        start = self.source.index("async def get_user_access_state(user_id: str) -> dict:")
        block = self.source[start:]

        self.assertIn('default = {"rol": "agente", "activo": True}', block)
        self.assertIn('rows = await get_rows(\n            "usuarios",', block)
        self.assertIn('"select": "rol,activo"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=8", block)
        self.assertIn('"rol": rows[0].get("rol") or "agente"', block)
        self.assertIn('"activo": rows[0].get("activo") if rows[0].get("activo") is not None else True', block)
        self.assertIn("except Exception:\n        pass\n    return default", block)
        self.assertNotIn("/rest/v1/usuarios", block)
        self.assertIn("from core.database import get_rows", self.source)
        self.assertIn(
            "from core.user_access import get_user_access_state, get_user_rol",
            self.main,
        )
        self.assertNotIn("async def get_user_access_state(", self.main)


if __name__ == "__main__":
    unittest.main()
