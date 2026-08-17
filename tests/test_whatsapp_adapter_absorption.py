from __future__ import annotations

import unittest

from scripts.refactor_whatsapp_adapter_into_canon import (
    ADAPTER,
    MARKER,
    THEME,
    WA,
    transform_text,
)


class WhatsAppAdapterAbsorptionTests(unittest.TestCase):
    def test_transform_moves_domain_rules_into_canon_only(self):
        theme = THEME.read_text(encoding="utf-8")
        whatsapp = WA.read_text(encoding="utf-8")
        adapter = ADAPTER.read_text(encoding="utf-8")
        new_theme, new_whatsapp = transform_text(theme, whatsapp, adapter)

        self.assertIn(MARKER, new_theme)
        self.assertIn('body[data-app="whatsapp"]', new_theme)
        self.assertIn("var(--sky-blue)", new_theme)
        self.assertIn("var(--line-2)", new_theme)
        self.assertNotIn("broquer-ui.css", new_whatsapp)
        self.assertIn('href="brokr-theme.css"', new_whatsapp)
        # Dense chat selectors must survive the move.
        self.assertIn(".w2-row--out .w2-bubble", new_theme)
        self.assertIn(".w2-conv__unread", new_theme)
        self.assertIn(".w2-tab.is-active", new_theme)


if __name__ == "__main__":
    unittest.main()
