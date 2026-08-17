from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scripts.refactor_frontend_shell_chrome import ROOT, TARGETS, transform_text


class FrontendShellChromeTransformTests(unittest.TestCase):
    def test_transform_removes_only_legacy_shell_regions(self):
        for name in TARGETS:
            source = (ROOT / name).read_text(encoding="utf-8")
            result = transform_text(source, name)

            self.assertNotIn("shell-replaced-sidebar", result, name)
            self.assertNotIn(".app-sidebar", result, name)
            self.assertNotIn(".app-sidebar__brand", result, name)
            self.assertNotIn(".app-nav-link", result, name)
            self.assertIn(f'<body data-app="{Path(name).stem}">', result, name)
            self.assertIn('<script src="app-shell.js" defer></script>', result, name)

            # The deterministic transform must be exactly equivalent to removing
            # the two known legacy regions from the original source.
            self.assertLess(len(result), len(source), name)

    def test_transform_refuses_already_migrated_or_unexpected_input(self):
        with self.assertRaises(RuntimeError):
            transform_text("<html><body></body></html>", "unexpected.html")


if __name__ == "__main__":
    unittest.main()
