"""Permanent guards for Lead Ads anti-replay and ledger Core delegation."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "facebook_leadgen_processor.py"


class MainFbLeadReplayLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CORE.read_text(encoding="utf-8")

    def test_ledger_read_and_write_are_both_routed_through_core(self):
        source = self.source
        self.assertNotIn("/rest/v1/fb_leads_recibidos", source)
        self.assertIn('await post_rows(\n                    "fb_leads_recibidos",', source)
        self.assertIn('accepted_statuses=(200, 201, 204)', source)
        self.assertIn('exc.response.status_code != 409', source)
        self.assertIn('not facebook_table_missing(exc.response)', source)

    def test_lookup_uses_core_and_preserves_fail_soft_contract(self):
        source = self.source
        self.assertIn('previous_rows = await get_rows(\n                "fb_leads_recibidos",', source)
        self.assertIn('"leadgen_id": f"eq.{leadgen_id}"', source)
        self.assertIn('"select": "id,procesado"', source)
        self.assertIn('"limit": "1"', source)
        self.assertIn("timeout=10", source)
        self.assertIn("except httpx.HTTPStatusError as exc:", source)
        self.assertIn("if facebook_table_missing(exc.response):", source)
        self.assertIn('warn_facebook_migration("procesar lead", exc.response)', source)
        self.assertIn("previous_rows = []", source)
        self.assertIn('if previous_rows and (previous_rows[0] or {}).get("procesado"):', source)
        self.assertIn('except Exception:\n        pass', source)
        compile(source, "core/facebook_leadgen_processor.py", "exec")


if __name__ == "__main__":
    unittest.main()
