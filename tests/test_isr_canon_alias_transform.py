from __future__ import annotations

import unittest

from scripts.refactor_isr_canon_aliases import ALIASES, PATH, transform_text


class IsrCanonAliasTransformTests(unittest.TestCase):
    def test_transform_removes_local_alias_root_without_changing_structure(self):
        source = PATH.read_text(encoding="utf-8")
        result = transform_text(source)
        self.assertNotIn(":root {", result)
        for legacy in ALIASES:
            self.assertNotIn(f"var({legacy})", result, legacy)
        self.assertIn('href="brokr-theme.css"', result)
        self.assertIn('<body data-app="isr">', result)
        self.assertIn('<script src="app-shell.js" defer></script>', result)
        self.assertLess(len(result), len(source))

    def test_transform_refuses_input_without_expected_root(self):
        with self.assertRaises(RuntimeError):
            transform_text("<html></html>")


if __name__ == "__main__":
    unittest.main()
