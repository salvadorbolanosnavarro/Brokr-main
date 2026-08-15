"""Permanent regression guard for Finanzas canonical PDF design tokens."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class FinanzasPdfDesignRegressionTests(unittest.TestCase):
    def test_router_uses_canonical_pdf_palette(self):
        source = (ROOT / "routers" / "finanzas.py").read_text(encoding="utf-8")

        self.assertIn("from core.design import pdf_palette", source)
        self.assertIn("_PDF_TOKENS = pdf_palette()", source)
        for copied in (
            "#0B0B0F", "#05203C", "#0A5DE0", "#5A6478",
            "#E4E8F0", "#F6F8FB", "#12A150", "#F7740D",
        ):
            self.assertNotIn(copied, source)
        self.assertIn("def _html_reporte", source)
        compile(source, "routers/finanzas.py", "exec")


if __name__ == "__main__":
    unittest.main()
