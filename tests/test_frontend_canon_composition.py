"""Guards for app-level composition, not just token compliance."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MARKER = "/* CANON-COMPOSITION-NORMALIZATION */"


class FrontendCanonCompositionTests(unittest.TestCase):
    def test_estadisticas_uses_neutral_app_header(self):
        text = (ROOT / "estadisticas.html").read_text(encoding="utf-8")
        self.assertIn(MARKER, text)
        normalized = text.split(MARKER, 1)[1]
        self.assertIn(".es-hero {\n  background: var(--paper);", normalized)
        self.assertIn(".es-hero h1 { color: var(--ink); }", normalized)
        self.assertIn("margin: 0 36px;", normalized)
        self.assertNotIn("linear-gradient", normalized.split("</style>", 1)[0])

    def test_estadisticas_tabs_are_integrated_not_floating_card_skin(self):
        text = (ROOT / "estadisticas.html").read_text(encoding="utf-8")
        normalized = text.split(MARKER, 1)[1].split("</style>", 1)[0]
        self.assertIn("border-bottom: 1px solid var(--line-2);", normalized)
        self.assertIn("border-bottom-color: var(--sky-blue);", normalized)
        self.assertIn("box-shadow: none;", normalized)

    def test_avm_uses_neutral_app_header_and_tabs(self):
        text = (ROOT / "avm.html").read_text(encoding="utf-8")
        self.assertIn(MARKER, text)
        normalized = text.split(MARKER, 1)[1].split("</style>", 1)[0]
        self.assertIn(".avm-header {\n  background: var(--paper);", normalized)
        self.assertIn(".avm-title {\n  color: var(--ink);", normalized)
        self.assertIn(".avm-tabs {\n  background: var(--paper);", normalized)
        self.assertIn("border-bottom-color: var(--sky-blue);", normalized)


if __name__ == "__main__":
    unittest.main()
