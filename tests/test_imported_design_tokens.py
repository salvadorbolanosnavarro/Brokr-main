"""PDF renderers must resolve the approved shared tokens without a browser."""
from pathlib import Path
import tempfile
import unittest
from core.design import load_theme_tokens,pdf_palette
from core.pdf_design import theme_css_for_pdf

class ImportedDesignTokensTests(unittest.TestCase):
    def test_local_import_aliases_parent_precedence_and_no_network(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'tokens.css').write_text(':root{--base:42px;--nested:var(--base);--same:child;}')
            (root/'theme.css').write_text('@import url("tokens.css");@import url("https://invalid.example/no.css");:root{--size:var(--nested);--same:parent;}')
            tokens=load_theme_tokens(root/'theme.css')
            self.assertEqual(tokens['size'],'42px');self.assertEqual(tokens['same'],'parent')
    def test_imported_palette_and_pdf_css_have_concrete_values(self):
        self.assertTrue(all('var('not in value for value in pdf_palette().values()))
        css=theme_css_for_pdf();self.assertIn('--ui-ink:',css);self.assertIn('family=Manrope',css)
        self.assertNotIn('--ink:var(',css)
    def test_alias_cycles_fail_explicitly(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'theme.css';path.write_text(':root{--a:var(--b);--b:var(--a);}')
            with self.assertRaisesRegex(RuntimeError,'Cyclic'):load_theme_tokens(path)
    def test_imports_cannot_escape_theme_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'theme.css').write_text('@import url("../outside.css");:root{--a:1;}')
            with self.assertRaises(ValueError):load_theme_tokens(root/'theme.css')
