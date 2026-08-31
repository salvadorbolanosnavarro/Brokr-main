"""Permanent guard for Facebook lead-log persistence through Core."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
CORE = ROOT / "core" / "facebook_leadgen_processor.py"


def async_function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(
        item for item in tree.body
        if isinstance(item, ast.AsyncFunctionDef) and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


class MainFbLeadLogPostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = CORE.read_text(encoding="utf-8")
        cls.function = async_function_source(cls.source, "process_facebook_lead")
        start = cls.function.index("async def _annotate(extra: dict) -> None:")
        end = cls.function.index("try:\n        try:\n            previous_rows", start)
        cls.block = cls.function[start:end]

    def test_lead_log_post_delegates_to_core(self):
        block = self.block
        self.assertIn('await post_rows(', block)
        self.assertIn('"fb_leads_recibidos"', block)
        self.assertIn('{**ledger, **extra}', block)
        self.assertIn('prefer="return=minimal"', block)
        self.assertIn('timeout=10', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertNotIn('/rest/v1/fb_leads_recibidos', block)

    def test_duplicate_missing_table_and_logging_contract_stays_intact(self):
        block = self.block
        self.assertIn('except httpx.HTTPStatusError as exc:', block)
        self.assertIn('exc.response.status_code != 409', block)
        self.assertIn('not facebook_table_missing(exc.response)', block)
        self.assertIn('leadgen_id,', block)
        self.assertIn('exc.response.status_code', block)
        self.assertIn('(exc.response.text or "")[:200]', block)
        self.assertIn('except Exception as exc:', block)
        self.assertIn('_log.error("Error anotando el lead %s: %s", leadgen_id, exc)', block)
        compile(self.source, "core/facebook_leadgen_processor.py", "exec")


if __name__ == "__main__":
    unittest.main()
