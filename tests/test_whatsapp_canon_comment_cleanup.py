from __future__ import annotations

import unittest

from scripts.refactor_whatsapp_canon_comment import COMMENT, PATH, transform_text


class WhatsAppCanonCommentCleanupTests(unittest.TestCase):
    def test_cleanup_only_removes_migration_comment_and_shrinks_file(self):
        source = PATH.read_text(encoding="utf-8")
        result = transform_text(source)
        self.assertNotEqual(source, result)
        self.assertNotIn(COMMENT, result)
        self.assertIn('href="brokr-theme.css"', result)
        self.assertNotIn("broquer-ui.css", result)
        self.assertLess(len(result.encode("utf-8")), len(source.encode("utf-8")))


if __name__ == "__main__":
    unittest.main()
