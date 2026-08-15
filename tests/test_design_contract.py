"""Regression tests for the executable Broquer design contract."""
import unittest

from core.design import pdf_palette, theme_css, theme_tokens


class DesignContractTests(unittest.TestCase):
    def test_canonical_theme_is_loadable(self):
        css = theme_css()
        self.assertIn(":root", css)
        self.assertIn('Edición "Canon"', css)

    def test_pdf_palette_is_derived_from_theme_tokens(self):
        tokens = theme_tokens()
        palette = pdf_palette()

        expected_sources = {
            "ink": "ink",
            "navy": "sky-navy",
            "blue": "sky-blue",
            "mute": "mute",
            "line": "line",
            "paper2": "paper-2",
            "green": "success",
            "orange": "warn",
        }
        for semantic_name, token_name in expected_sources.items():
            with self.subTest(semantic_name=semantic_name):
                self.assertEqual(palette[semantic_name], tokens[token_name])

    def test_canon_uses_single_inter_family_aliases(self):
        tokens = theme_tokens()
        for token_name in ("font-sans", "font-display", "font-mono", "font-serif"):
            with self.subTest(token_name=token_name):
                self.assertIn("Inter", tokens[token_name])


if __name__ == "__main__":
    unittest.main()
