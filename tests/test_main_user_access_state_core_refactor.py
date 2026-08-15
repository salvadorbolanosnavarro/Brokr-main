"""Permanent guards for get_user_access_state's Core database contract."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainUserAccessStateCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_main_compiles(self):
        compile(self.source, "main.py", "exec")

    def test_access_state_keeps_fail_soft_defaults_and_uses_core(self):
        start = self.source.index("async def get_user_access_state(user_id: str) -> dict:")
        end = self.source.index("# ─────────────────────────────────────────────\n# TELEMETRÍA", start)
        block = self.source[start:end]

        self.assertIn('default = {"rol": "agente", "activo": True}', block)
        self.assertIn('rows = await get_rows(\n            "usuarios",', block)
        self.assertIn('"select": "rol,activo"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=8", block)
        self.assertIn('"rol": rows[0].get("rol") or "agente"', block)
        self.assertIn('"activo": rows[0].get("activo") if rows[0].get("activo") is not None else True', block)
        self.assertIn("except Exception:\n        pass\n    return default", block)
        self.assertNotIn("/rest/v1/usuarios", block)
        self.assertNotIn('"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"', block)


if __name__ == "__main__":
    unittest.main()
