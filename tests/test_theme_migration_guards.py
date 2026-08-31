"""Guards for retiring the temporary v2 theme without creating new consumers."""
from __future__ import annotations

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
LEGACY_THEME = "brokr-theme-v2.css"
ALLOWED_TEMPORARY_CONSUMERS = {"estadisticas.html"}


class ThemeMigrationGuards(unittest.TestCase):
    def test_no_new_html_consumers_of_legacy_theme(self):
        consumers = set()
        for path in ROOT.glob("*.html"):
            text = path.read_text(encoding="utf-8")
            if LEGACY_THEME in text:
                consumers.add(path.name)

        unexpected = consumers - ALLOWED_TEMPORARY_CONSUMERS
        self.assertFalse(
            unexpected,
            "Temporary v2 theme gained new consumers: " + ", ".join(sorted(unexpected)),
        )

    def test_known_temporary_consumer_is_explicit(self):
        path = ROOT / "estadisticas.html"
        text = path.read_text(encoding="utf-8")
        self.assertIn(LEGACY_THEME, text)

    def test_legacy_theme_is_only_a_canon_compatibility_shim(self):
        text = (ROOT / LEGACY_THEME).read_text(encoding="utf-8")
        self.assertIn('@import url("brokr-theme.css")', text)
        self.assertNotRegex(
            text,
            re.compile(r"--[A-Za-z0-9_-]+\s*:"),
            "brokr-theme-v2.css must not define its own design tokens",
        )
        self.assertIn("Remove this shim", text)


if __name__ == "__main__":
    unittest.main()
