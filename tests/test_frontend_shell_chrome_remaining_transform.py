from __future__ import annotations

import unittest

from scripts.refactor_frontend_shell_chrome_remaining import (
    ROOT,
    transform_isr,
    transform_propiedades,
)


class RemainingFrontendShellChromeTransformTests(unittest.TestCase):
    def test_isr_transform_is_narrow_and_preserves_shell_owner(self):
        source = (ROOT / "isr.html").read_text(encoding="utf-8")
        result = transform_isr(source)
        self.assertNotIn("shell-replaced-sidebar", result)
        self.assertNotIn(".app-sidebar", result)
        self.assertIn('<script src="app-shell.js" defer></script>', result)
        self.assertIn(":root {", result, "ISR token-root debt is intentionally a separate migration")
        self.assertLess(len(result), len(source))

    def test_propiedades_transform_is_narrow_and_preserves_shell_owner(self):
        source = (ROOT / "propiedades.html").read_text(encoding="utf-8")
        result = transform_propiedades(source)
        self.assertNotIn("shell-replaced-sidebar", result)
        self.assertNotIn(".app-sidebar", result)
        self.assertIn('<script src="app-shell.js" defer></script>', result)
        self.assertLess(len(result), len(source))

    def test_transforms_refuse_unexpected_input(self):
        with self.assertRaises(RuntimeError):
            transform_isr("<html></html>")
        with self.assertRaises(RuntimeError):
            transform_propiedades("<html></html>")


if __name__ == "__main__":
    unittest.main()
