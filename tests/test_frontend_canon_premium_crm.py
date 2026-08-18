"""Permanent guards for the premium Propiedades + Contactos composition pass."""
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "brokr-theme.css"
MARKER = "/* BROQUER-PREMIUM-PROPERTIES-CONTACTS"


class PremiumPropertiesContactsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = THEME.read_text(encoding="utf-8")
        cls.premium = cls.text.split(MARKER, 1)[1]

    def test_rules_live_in_canon_theme_and_are_scoped(self):
        self.assertIn(MARKER, self.text)
        self.assertIn('body[data-app="propiedades"]', self.premium)
        self.assertIn('body[data-app="contactos"]', self.premium)

    def test_propiedades_has_editorial_catalog_hierarchy(self):
        self.assertIn('.prop-card-img { aspect-ratio: 16 / 10; }', self.premium)
        self.assertIn('font-size: var(--fs-h2);\n  font-weight: 800;', self.premium)
        self.assertIn('.prop-act-btn {\n  height: var(--h-sm);\n  border: 0;', self.premium)
        self.assertIn('.props-toolbar {\n  gap: var(--sp-2);', self.premium)

    def test_contactos_is_dense_on_desktop(self):
        self.assertIn('.page-head {\n  position: relative;', self.premium)
        self.assertIn('.contact-card {\n  min-height: 72px;', self.premium)
        self.assertIn('border-radius: 0;\n  background: var(--paper);', self.premium)
        self.assertIn('.ftab.active {\n  color: var(--ink);\n  border-bottom-color: var(--sky-blue);', self.premium)

    def test_contactos_restores_touch_cards_on_mobile(self):
        mobile = self.premium.split('@media (max-width: 720px)', 1)[1]
        self.assertIn('body[data-app="contactos"] .contact-card {', mobile)
        self.assertIn('border-radius: var(--r-lg);', mobile)
        self.assertIn('border: 1px solid var(--line-2);', mobile)


if __name__ == "__main__":
    unittest.main()
