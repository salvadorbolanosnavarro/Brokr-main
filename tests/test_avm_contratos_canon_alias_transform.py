from __future__ import annotations

import unittest

from scripts.refactor_avm_contratos_canon_aliases import (
    AVM_ALIASES,
    CONTRATOS_ALIASES,
    ROOT,
    transform_avm,
    transform_contratos,
)


class AvmContratosCanonAliasTransformTests(unittest.TestCase):
    def test_contratos_transform_is_exact_and_removes_alias_root(self):
        source = (ROOT / "contratos.html").read_text(encoding="utf-8")
        result = transform_contratos(source)
        self.assertNotEqual(result, source)
        self.assertNotIn("\n:root{\n  --navy:", result)
        for alias in CONTRATOS_ALIASES:
            self.assertNotIn(f"var({alias})", result)
        self.assertIn('href="brokr-theme.css"', result)
        self.assertIn('<script src="app-shell.js" defer></script>', result)

    def test_avm_transform_removes_override_alias_root_but_keeps_safe_area(self):
        source = (ROOT / "avm.html").read_text(encoding="utf-8")
        result = transform_avm(source)
        self.assertNotEqual(result, source)
        self.assertNotIn('--navy: var(--sky-navy) !important;', result)
        for alias in AVM_ALIASES:
            self.assertNotIn(f"var({alias})", result)
        self.assertIn(':root { --safe-top: max(env(safe-area-inset-top, 0px), 44px); }', result)
        self.assertIn('href="brokr-theme.css"', result)
        self.assertIn('<script src="app-shell.js" defer></script>', result)


if __name__ == "__main__":
    unittest.main()
