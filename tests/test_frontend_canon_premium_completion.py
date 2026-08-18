import unittest
from pathlib import Path


class PremiumUXCompletionContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.css = Path('brokr-theme.css').read_text(encoding='utf-8')

    def test_completion_marker_exists(self):
        self.assertIn('/* BROQUER-PREMIUM-UX-COMPLETION */', self.css)

    def test_leads_is_dense_crm_not_sticky_local_chrome(self):
        self.assertIn('body[data-app="leads"] .page-head {', self.css)
        self.assertIn('position: relative;', self.css)
        self.assertIn('body[data-app="leads"] .list .contact-card {', self.css)
        self.assertIn('border-radius: 0;', self.css)

    def test_contracts_use_canonical_form_width_and_cards(self):
        self.assertIn('body[data-app="contratos"] #wrap {', self.css)
        self.assertIn('max-width: var(--form-max);', self.css)
        self.assertIn('body[data-app="contratos"] .card {', self.css)

    def test_isr_is_calm_high_trust_form(self):
        self.assertIn('body[data-app="isr"] .page-scroll {', self.css)
        self.assertIn('body[data-app="isr"] .card {', self.css)
        self.assertIn('box-shadow: none !important;', self.css)

    def test_compliance_has_no_decorative_navy_hero(self):
        self.assertIn('body[data-app="cumplimiento"] .cp-ley {', self.css)
        self.assertIn('background: var(--bone);', self.css)
        self.assertIn('body[data-app="cumplimiento"] .cp-ley p { color: var(--ink-2); }', self.css)

    def test_facebook_ads_starts_as_product_tool(self):
        self.assertIn('.fa-wrap .fa-hero {', self.css)
        self.assertIn('.fa-wrap .fa-hero::after { display: none; }', self.css)
        self.assertIn('.fa-wrap .fa-tabs {', self.css)

    def test_secondary_modules_share_canon_density(self):
        for selector in (
            'body[data-app="finanzas"] .fin-scroll',
            'body[data-app="video"] .vid-scroll',
            'body[data-app="mi-sitio"] .ms-body',
            'body[data-app="equipo"] .eq-scroll',
            '.ac-root .ac-top',
            'body[data-app="bandeja"] .bx-list',
        ):
            self.assertIn(selector, self.css)

    def test_admin_does_not_keep_independent_navy_topbar(self):
        self.assertIn('.ac-root .ac-top {', self.css)
        self.assertIn('background: var(--paper);', self.css)


if __name__ == '__main__':
    unittest.main()
