from __future__ import annotations

import unittest

from scripts.refactor_image_cleaner_canon import ALIASES, PATH, transform_text


class ImageCleanerCanonTransformTests(unittest.TestCase):
    def test_transform_removes_local_alias_root_and_hidden_shell_copy(self):
        source = PATH.read_text(encoding="utf-8")
        result = transform_text(source)
        self.assertNotEqual(source, result)
        self.assertNotRegex(result, r"(?m)^\s*:root\s*\{")
        self.assertNotIn("shell-replaced-sidebar", result)
        self.assertNotIn(".app-sidebar", result)
        for alias in ALIASES:
            self.assertNotIn(f"var({alias})", result)
        self.assertIn('href="brokr-theme.css"', result)
        self.assertIn('<script src="app-shell.js" defer></script>', result)
        self.assertIn("function useInFicha()", result)
        self.assertIn("function useInFacebookAds()", result)
        self.assertIn("function useInVideo()", result)


if __name__ == "__main__":
    unittest.main()
