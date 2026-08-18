"""Permanent guards for /profile/status integration reads delegated to Core."""
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainProfileStatusCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.get("/profile/status")')
        end = cls.source.index(
            "# ────────────────────────────────────────────\n# CLAUDE CHAT PROXY — BROQ IA SUPERINTELIGENTE",
            start,
        )
        cls.block = cls.source[start:end]
        integrations_end = cls.block.index("    # Parsear cada provider")
        cls.integrations_block = cls.block[:integrations_end]

    def test_main_compiles(self):
        compile(self.source, "main.py", "exec")

    def test_profile_status_uses_core_and_keeps_fail_soft_contract(self):
        block = self.integrations_block
        self.assertIn('rows = await get_rows(\n            "user_integrations",', block)
        self.assertIn('"provider": "in.(easybroker,facebook)"', block)
        self.assertIn('"select": "provider,api_key,meta"', block)
        self.assertIn("timeout=8", block)
        self.assertIn(
            'except Exception:\n        return {"eb": {"configured": False, "masked": ""}, "fb": {"connected": False}}',
            block,
        )
        self.assertNotIn("/rest/v1/user_integrations", block)
        self.assertNotIn('"Authorization": f"Bearer {SUPABASE_SERVICE_KEY}"', block)


if __name__ == "__main__":
    unittest.main()
