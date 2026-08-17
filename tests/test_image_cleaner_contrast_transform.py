from __future__ import annotations

import unittest

from scripts.refactor_image_cleaner_contrast import PATH, transform_text


class ImageCleanerContrastTransformTests(unittest.TestCase):
    def test_four_secondary_text_selectors_move_to_readable_mute(self):
        source = PATH.read_text(encoding="utf-8")
        result = transform_text(source)
        self.assertNotEqual(source, result)
        for selector in (".drop-types", ".prompt-hint", ".card-status", ".empty"):
            start = result.index(selector)
            snippet = result[start:start + 180]
            self.assertIn("color:var(--mute)", snippet, selector)
            self.assertNotIn("color:var(--mute-3)", snippet, selector)
        self.assertIn("function useInFicha()", result)
        self.assertIn("function useInFacebookAds()", result)
        self.assertIn("function useInVideo()", result)


if __name__ == "__main__":
    unittest.main()
