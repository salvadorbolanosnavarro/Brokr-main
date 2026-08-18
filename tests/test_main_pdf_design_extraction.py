"""Permanent guard for main.py PDF design bridge extraction."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainPdfDesignExtractionTests(unittest.TestCase):
    def test_main_delegates_legacy_pdf_theme_bridge_to_core(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        core = (ROOT / "core" / "pdf_design.py").read_text(encoding="utf-8")

        self.assertIn("from core.pdf_design import theme_css_for_pdf", main)
        self.assertNotIn("_THEME_TOKENS_FALLBACK", main)
        self.assertNotIn("def _theme_tokens()", main)
        self.assertNotIn("def theme_css_for_pdf(", main)
        self.assertIn('Path(__file__).resolve().parents[1] / "brokr-theme.css"', core)
        self.assertIn("_THEME_TOKENS_FALLBACK", core)
        self.assertIn('for required in ("--ink", "--sky-navy", "--sky-blue", "--font-sans")', core)
        self.assertIn("using respaldo", core)
        self.assertIn("def theme_css_for_pdf(extra: str = \"\") -> str:", core)
        compile(core, "core/pdf_design.py", "exec")
        compile(main, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
