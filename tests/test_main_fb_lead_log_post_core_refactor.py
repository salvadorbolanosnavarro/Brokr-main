"""Permanent guard for Facebook lead-log persistence through Core."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainFbLeadLogPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index("async def _fb_procesar_lead(valor: dict) -> None:")
        end = cls.source.index("# ── 0. ¿Ya lo procesamos?", start)
        cls.block = cls.source[start:end]

    def test_lead_log_post_delegates_to_core(self):
        block = self.block
        self.assertIn('await post_rows(', block)
        self.assertIn('"fb_leads_recibidos"', block)
        self.assertIn('{**bitacora, **extra}', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=10', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertNotIn('/rest/v1/fb_leads_recibidos', block)

    def test_duplicate_missing_table_and_logging_contract_stays_intact(self):
        block = self.block
        self.assertIn('except httpx.HTTPStatusError as e:', block)
        self.assertIn('e.response.status_code != 409', block)
        self.assertIn('not _fb_tabla_falta(e.response)', block)
        self.assertIn('leadgen_id, e.response.status_code', block)
        self.assertIn('(e.response.text or "")[:200]', block)
        self.assertIn('except Exception as e:', block)
        self.assertIn('_fb_log.error("Error anotando el lead %s: %s", leadgen_id, e)', block)
        compile(self.source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
