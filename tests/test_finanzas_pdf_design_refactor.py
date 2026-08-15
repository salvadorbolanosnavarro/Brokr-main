"""Dry-run the Finanzas PDF design migration against current source."""
from __future__ import annotations

from pathlib import Path
import unittest

from scripts.refactor_finanzas_pdf_design import transform

ROOT = Path(__file__).resolve().parents[1]


class FinanzasPdfDesignRefactorTests(unittest.TestCase):
    def test_transform_uses_canonical_pdf_palette_and_compiles(self):
        source = (ROOT / "routers" / "finanzas.py").read_text(encoding="utf-8")
        updated = transform(source)

        self.assertIn("from core.design import pdf_palette", updated)
        self.assertIn("_PDF_TOKENS = pdf_palette()", updated)
        for copied in (
            "#0B0B0F", "#05203C", "#0A5DE0", "#5A6478",
            "#E4E8F0", "#F6F8FB", "#12A150", "#F7740D",
        ):
            self.assertNotIn(copied, updated)
        self.assertIn("def _html_reporte", updated)
        compile(updated, "routers/finanzas.py", "exec")


if __name__ == "__main__":
    unittest.main()
