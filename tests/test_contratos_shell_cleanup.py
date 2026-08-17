from __future__ import annotations

import unittest

from scripts.refactor_contratos_shell_cleanup import PATH, transform_text


class ContratosShellCleanupTests(unittest.TestCase):
    def test_transform_removes_only_hidden_shell_copy(self):
        source = PATH.read_text(encoding="utf-8")
        result = transform_text(source)
        self.assertNotEqual(source, result)
        self.assertNotIn("shell-replaced-sidebar", result)
        self.assertNotIn('<aside class="app-sidebar">', result)
        self.assertIn('<script src="app-shell.js" defer></script>', result)
        self.assertIn('id="form-arrendamiento"', result)
        self.assertIn('id="form-promesa"', result)
        self.assertIn('function generarContrato', result)


if __name__ == "__main__":
    unittest.main()
