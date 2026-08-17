from __future__ import annotations

import re
import unittest

from scripts.refactor_landing_canon import PATH, transform_text


class LandingCanonTransformTests(unittest.TestCase):
    def test_transform_removes_parallel_b2_design_system(self):
        source = PATH.read_text(encoding="utf-8")
        result = transform_text(source)
        self.assertNotEqual(source, result)
        self.assertIn('href="brokr-theme.css"', result)
        self.assertNotIn("fonts.googleapis.com", result)
        self.assertNotIn("fonts.gstatic.com", result)
        self.assertNotRegex(result, r"(?m)^\s*:root\s*\{")
        self.assertFalse(re.search(r"--(?:b2|fs2|r2|sh2|ease2)[\w-]*", result))
        for token in (
            "var(--sky-blue)", "var(--sky-navy)", "var(--paper)",
            "var(--ink)", "var(--line)", "var(--success)",
            "var(--danger)", "var(--r-lg)", "var(--shadow-sm)",
        ):
            self.assertIn(token, result)
        # Preserve marketing/product content and conversion paths.
        self.assertIn("AI Real Estate Operating System", result)
        self.assertIn("Broq", result)
        self.assertIn("login.html", result)
        self.assertIn("registro.html", result)
        self.assertIn("<video", result)


if __name__ == "__main__":
    unittest.main()
