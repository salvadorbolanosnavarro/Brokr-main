"""Regression guards for Broquer's single-source design contract."""
from __future__ import annotations

from pathlib import Path
import unittest

from core.design import pdf_palette, theme_tokens


ROOT = Path(__file__).resolve().parents[1]


class DesignSourceOfTruthTests(unittest.TestCase):
    def test_design_document_points_to_executable_theme(self):
        text = (ROOT / "DESIGN.md").read_text(encoding="utf-8")
        self.assertIn("brokr-theme.css", text)
        self.assertIn("Canon", text)
        self.assertIn("fuente", text.lower())

    def test_backend_design_reader_has_no_copied_hex_palette(self):
        text = (ROOT / "core/design.py").read_text(encoding="utf-8")
        self.assertNotRegex(text, r"#[0-9A-Fa-f]{6}\b")
        self.assertIn("brokr-theme.css", text)

    def test_pdf_palette_resolves_from_current_theme(self):
        tokens = theme_tokens()
        palette = pdf_palette()
        self.assertEqual(palette["ink"], tokens["ink"])
        self.assertEqual(palette["navy"], tokens["sky-navy"])
        self.assertEqual(palette["blue"], tokens["sky-blue"])
        self.assertEqual(palette["green"], tokens["success"])
        self.assertEqual(palette["orange"], tokens["warn"])


if __name__ == "__main__":
    unittest.main()
