from pathlib import Path

THEME = Path('brokr-theme.css')
TEST = Path('tests/test_frontend_canon_premium_completion.py')
MARKER = '/* BROQUER-PREMIUM-UX-COMPLETION */'

text = THEME.read_text(encoding='utf-8')
if MARKER in text:
    print('premium UX completion already present')
    raise SystemExit(0)

css = r'''

/* BROQUER-PREMIUM-UX-COMPLETION */
/* Final product-composition pass. These are visual-only overrides scoped to
   active modules. They do not own markup, navigation, IDs, APIs or behavior. */

/* ── Leads · dense CRM + calm pipeline ─────────────────────── */
body[data-app="leads"] .page-head {
  position: relative;
  top: auto;
  z-index: auto;
  padding: var(--sp-7) var(--pad-x) 0;
  background: var(--paper);
  border-bottom: 0;
}
body[data-app="leads"] .page-head__row { margin-bottom: var(--sp-5); }
body[data-app="leads"] .page-head h1 {
  font-size: var(--fs-h1);
  line-height: var(--lh-h1);
}
body[data-app="leads"] .page-head__count {
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  padding: 0 var(--sp-3);
  background: var(--paper-2);
  border: 0;
  letter-spacing: 0;
}
body[data-app="leads"] .head-search {
  width: 100%;
  max-width: none;
  height: var(--h);
  margin-bottom: var(--sp-2);
  padding: 0 var(--sp-4);
  border-radius: var(--r);
  border-color: var(--line-2);
  background: var(--paper-2);
}
body[data-app="leads"] .head-search:focus-within {
  background: var(--bone);
  border-color: var(--sky-blue);
  box-shadow: var(--focus);
}
body[data-app="leads"] .view-seg {
  min-height: var(--h-sm);
  border-color: var(--line-2);
}
body[data-app="leads"] .view-seg button { min-height: 32px; }
body[data-app="leads"] .filters-row {
  gap: var(--sp-2);
  margin-bottom: var(--sp-2);
}
body[data-app="leads"] .filtro-select {
  height: var(--h-sm);
  border-radius: var(--r-sm);
  border-color: var(--line-2);
  background-color: var(--bone);
  font-weight: 600;
}
body[data-app="leads"] .tabs {
  gap: var(--sp-6);
  border-bottom-color: var(--line-2);
}
body[data-app="leads"] .ftab {
  padding: var(--sp-3) 0;
  font-weight: 600;
}
body[data-app="leads"] .ftab.active {
  color: var(--ink);
  border-bottom-color: var(--sky-blue);
  font-weight: 700;
}
body[data-app="leads"] .add-btn,
body[data-app="leads"] .import-btn {
  height: var(--h);
  border-radius: var(--r-sm);
  font-weight: 700;
}
body[data-app="leads"] .add-btn { background: var(--sky-blue); }
body[data-app="leads"] .add-btn:hover { background: var(--sky-blue-press); opacity: 1; }
body[data-app="leads"] .import-btn { border-color: var(--line-2); }
body[data-app="leads"] .kanban {
  gap: var(--sp-3);
  padding: var(--sp-4) var(--pad-x) var(--sp-20);
}
body[data-app="leads"] .kb-col {
  border-color: var(--line-2);
  background: var(--paper-2);
  box-shadow: none;
}
body[data-app="leads"] .kb-col__head { padding: var(--sp-4) var(--sp-4) var(--sp-3); }
body[data-app="leads"] .kb-card {
  border-color: var(--line-2);
  box-shadow: var(--shadow-xs);
}
body[data-app="leads"] .kb-card:hover {
  transform: translateY(-1px);
  border-color: var(--line-3);
  box-shadow: var(--shadow-sm);
}
body[data-app="leads"] .list {
  max-width: var(--page-max);
  margin: 0 auto;
  padding: var(--sp-4) var(--pad-x) var(--sp-20);
}
@media (min-width: 721px) {
  body[data-app="leads"] .list .contact-card {
    min-height: 72px;
    margin-bottom: 0;
    padding: var(--sp-3) var(--sp-2);
    border: 0;
    border-bottom: 1px solid var(--line);
    border-radius: 0;
    background: var(--paper);
    transform: none;
  }
  body[data-app="leads"] .list .contact-card:first-child { border-top: 1px solid var(--line); }
  body[data-app="leads"] .list .contact-card:hover {
    transform: none;
    background: var(--paper-2);
  }
}
body[data-app="leads"] .det-tab.active {
  color: var(--ink);
  border-bottom-color: var(--sky-blue);
}
body[data-app="leads"] .det-tab.active .n {
  background: var(--sky-blue);
  color: var(--bone);
}
body[data-app="leads"] .btn-primary,
body[data-app="leads"] .vinculo-form button,
body[data-app="leads"] .fab { background: var(--sky-blue); }
body[data-app="leads"] .empty {
  max-width: 620px;
  margin: var(--sp-6) auto;
  padding: var(--sp-12) var(--sp-7);
  border: 1px dashed var(--line-2);
  border-radius: var(--r-xl);
  background: var(--paper-2);
}

/* ── Contratos · professional document workflow ───────────── */
body[data-app="contratos"] #wrap {
  max-width: var(--form-max);
  padding: var(--sp-7) var(--pad-x) var(--sp-16);
}
body[data-app="contratos"] .doc-picker {
  gap: var(--sp-2);
  padding: var(--sp-2);
  margin-bottom: var(--sp-5);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  background: var(--paper-2);
}
body[data-app="contratos"] .doc-picker-btn,
body[data-app="contratos"] .doc-new-btn {
  min-height: var(--h);
  padding-top: 0;
  padding-bottom: 0;
  border-radius: var(--r-sm);
}
body[data-app="contratos"] .doc-picker-btn {
  border-color: var(--line-2);
  background: var(--bone);
}
body[data-app="contratos"] .doc-new-btn {
  border-color: var(--sky-blue);
  background: var(--sky-blue);
}
body[data-app="contratos"] .doc-new-btn:hover { background: var(--sky-blue-press); filter: none; }
body[data-app="contratos"] .doc-menu {
  border-color: var(--line-2);
  border-radius: var(--r-lg);
}
body[data-app="contratos"] .doc-menu-item:hover { background: var(--paper-2); }
body[data-app="contratos"] .card {
  padding: var(--sp-6);
  margin-bottom: var(--sp-4);
  border-color: var(--line-2);
  border-radius: var(--r-lg);
  box-shadow: none;
}
body[data-app="contratos"] .card-title {
  color: var(--ink-2);
  border-bottom-color: var(--line);
  letter-spacing: 0;
}
body[data-app="contratos"] .f input,
body[data-app="contratos"] .f select,
body[data-app="contratos"] .f textarea {
  background: var(--shell);
  border-color: var(--line-2);
}
body[data-app="contratos"] .f input:focus,
body[data-app="contratos"] .f select:focus,
body[data-app="contratos"] .f textarea:focus {
  background: var(--bone);
  border-color: var(--sky-blue);
  box-shadow: var(--focus);
}
body[data-app="contratos"] .gen-btn {
  min-height: var(--h-lg);
  padding: 0 var(--sp-6);
  border-radius: var(--r-sm);
  background: var(--sky-blue);
  font-weight: 700;
}
body[data-app="contratos"] .gen-btn:hover { background: var(--sky-blue-press); }
body[data-app="contratos"] .pick-btn {
  min-height: var(--h-sm);
  padding: 0 var(--sp-3);
  border: 1px solid var(--line-2);
  border-radius: var(--r-sm);
  background: var(--bone);
  color: var(--sky-blue);
  letter-spacing: 0;
}
body[data-app="contratos"] .pick-btn:hover {
  border-color: var(--sky-blue);
  background: var(--sky-canvas);
  color: var(--sky-blue-press);
}
body[data-app="contratos"] .clausulas-section {
  border: 1px solid var(--line-2);
  border-radius: var(--r-lg);
  padding: var(--sp-6);
}
body[data-app="contratos"] .btn-add-clausula {
  border-color: var(--line-3);
  color: var(--sky-blue);
}

/* ── ISR · calm, high-trust form ──────────────────────────── */
body[data-app="isr"] .page-scroll {
  max-width: var(--form-max);
  padding: var(--sp-6) var(--pad-x) var(--sp-20);
}
body[data-app="isr"] .card {
  padding: var(--sp-6) !important;
  margin-bottom: var(--sp-4) !important;
  border: 1px solid var(--line-2) !important;
  border-radius: var(--r-lg) !important;
  background: var(--bone) !important;
  box-shadow: none !important;
}
body[data-app="isr"] .card-label {
  margin-bottom: var(--sp-4);
  color: var(--ink-2) !important;
  font-size: var(--fs-label-2) !important;
  letter-spacing: 0;
}
body[data-app="isr"] .field input,
body[data-app="isr"] .field select,
body[data-app="isr"] .field textarea {
  min-height: var(--h);
  background: var(--shell) !important;
  border: 1px solid var(--line-2) !important;
  border-radius: var(--r) !important;
}
body[data-app="isr"] .field input:focus,
body[data-app="isr"] .field select:focus,
body[data-app="isr"] .field textarea:focus {
  background: var(--bone) !important;
  border-color: var(--sky-blue) !important;
  box-shadow: var(--focus) !important;
}
body[data-app="isr"] .terreno-help-btn {
  border-color: var(--line-2);
  border-style: solid;
  border-radius: var(--r-sm);
  color: var(--sky-blue);
}
body[data-app="isr"] .terreno-help {
  border-left-color: var(--sky-blue);
  background: var(--paper-2);
}
body[data-app="isr"] .isr-calc-btn,
body[data-app="isr"] .btn-calc,
body[data-app="isr"] .calc-btn {
  min-height: var(--h-lg) !important;
  border-radius: var(--r-sm) !important;
  background: var(--sky-blue) !important;
  color: var(--bone) !important;
  font-weight: 700 !important;
}

/* ── Bandeja · keep the three-lane model, refine density ─── */
body[data-app="bandeja"] .bx-list { width: 340px; }
body[data-app="bandeja"] .bx-search input {
  border-color: var(--line-2);
  border-radius: var(--r);
  background: var(--paper-2);
}
body[data-app="bandeja"] .bx-conv.is-active::before { background: var(--sky-blue); }
body[data-app="bandeja"] .bx-th-head { min-height: var(--h-lg); }
body[data-app="bandeja"] .bx-score {
  box-shadow: var(--shadow-xs);
}

/* ── Finanzas · toolbar + data surfaces ───────────────────── */
body[data-app="finanzas"] .fin-scroll {
  max-width: var(--page-max);
  padding: var(--sp-6) var(--pad-x) var(--sp-16);
}
body[data-app="finanzas"] .fin-acciones-head {
  gap: var(--sp-2);
  padding: var(--sp-2);
  margin-bottom: var(--sp-5);
  border: 1px solid var(--line);
  border-radius: var(--r-lg);
  background: var(--paper-2);
}
body[data-app="finanzas"] .fin-acciones-head .bk-btn { min-height: var(--h); }
body[data-app="finanzas"] .bk-card--raise {
  box-shadow: none;
  border-color: var(--line-2);
}
body[data-app="finanzas"] .fin-kpis .bk-card { min-height: 124px; }
body[data-app="finanzas"] .fin-periodo {
  padding-bottom: var(--sp-4);
  border-bottom: 1px solid var(--line);
}

/* ── Cumplimiento · legal context, not a navy hero ───────── */
body[data-app="cumplimiento"] .cp-scroll {
  max-width: var(--page-max);
  padding: var(--sp-6) var(--pad-x) var(--sp-16);
}
body[data-app="cumplimiento"] .cp-ley {
  background: var(--bone);
  color: var(--ink);
  border: 1px solid var(--line-2);
  border-radius: var(--r-lg);
  box-shadow: none;
}
body[data-app="cumplimiento"] .cp-ley__tile {
  background: var(--sky-canvas);
  color: var(--sky-blue);
}
body[data-app="cumplimiento"] .cp-ley__eyebrow,
body[data-app="cumplimiento"] .cp-ley strong {
  color: var(--sky-blue);
}
body[data-app="cumplimiento"] .cp-ley p { color: var(--ink-2); }
body[data-app="cumplimiento"] .cp-ley__pie {
  border-top-color: var(--line);
  color: var(--mute);
}
body[data-app="cumplimiento"] .cp-ley__link {
  color: var(--ink);
  border-color: var(--line-2);
  border-radius: var(--r-sm);
}
body[data-app="cumplimiento"] .cp-ley__link:hover { background: var(--paper-2); }
body[data-app="cumplimiento"] .cp-kpi {
  border-color: var(--line-2);
  box-shadow: none;
}

/* ── Facebook Ads · product tool, not a marketing landing ── */
.fa-wrap {
  max-width: var(--page-max);
  padding: var(--sp-7) var(--pad-x) var(--sp-20);
}
.fa-wrap .fa-hero {
  padding: 0 0 var(--sp-6);
  margin-bottom: var(--sp-5);
  overflow: visible;
  background: var(--paper);
  border: 0;
  border-radius: 0;
}
.fa-wrap .fa-hero::after { display: none; }
.fa-wrap .fa-eyebrow {
  color: var(--sky-blue);
  font-weight: 700;
}
.fa-wrap .fa-hero h1 {
  font-size: var(--fs-h1);
  line-height: var(--lh-h1);
  max-width: 760px;
}
.fa-wrap .fa-hero h1 span { color: var(--ink); }
.fa-wrap .fa-tabs {
  gap: var(--sp-6);
  padding: 0;
  margin-bottom: var(--sp-5);
  background: transparent;
  border: 0;
  border-bottom: 1px solid var(--line-2);
  border-radius: 0;
}
.fa-wrap .fa-tab {
  flex: 0 0 auto;
  padding: 0 0 var(--sp-3);
  margin-bottom: -1px;
  border-bottom: 2px solid transparent;
  border-radius: 0;
}
.fa-wrap .fa-tab.active {
  background: transparent;
  color: var(--ink);
  border-bottom-color: var(--sky-blue);
  box-shadow: none;
}
.fa-wrap .fa-card,
.fa-wrap .fa-conn-card,
.fa-wrap .fa-banner {
  border-color: var(--line-2);
  box-shadow: none;
}
.fa-wrap .fa-card { padding: var(--sp-6); }
.fa-wrap .fa-field input,
.fa-wrap .fa-field textarea {
  min-height: var(--h);
  background: var(--shell);
  border-color: var(--line-2);
}
.fa-wrap .fa-field input:focus,
.fa-wrap .fa-field textarea:focus {
  background: var(--bone);
  border-color: var(--sky-blue);
  box-shadow: var(--focus);
}
.fa-wrap .fa-btn {
  min-height: var(--h);
  padding: 0 var(--sp-5);
  border-radius: var(--r-sm);
}
.fa-wrap .fa-btn-primary { background: var(--sky-blue); }
.fa-wrap .fa-btn-primary:hover { background: var(--sky-blue-press); }

/* ── Video · creation workspace ───────────────────────────── */
body[data-app="video"] .vid-scroll {
  max-width: var(--page-max);
  padding: var(--sp-6) var(--pad-x) var(--sp-16);
}
body[data-app="video"] .vid-buscar { max-width: 760px; }
body[data-app="video"] .bk-card--raise {
  box-shadow: none;
  border-color: var(--line-2);
}
body[data-app="video"] .vid-ed-card,
body[data-app="video"] .vid-fmt {
  border-color: var(--line-2);
  border-radius: var(--r-lg);
}
body[data-app="video"] .vid-ed-card.is-sel,
body[data-app="video"] .vid-fmt.is-sel {
  border-color: var(--sky-blue);
  box-shadow: var(--focus);
}

/* ── Mi sitio · configuration, not a card gallery ─────────── */
body[data-app="mi-sitio"] .ms-body {
  max-width: var(--form-max);
  padding: var(--sp-6) var(--pad-x) var(--sp-20);
}
body[data-app="mi-sitio"] .ms-activar {
  padding: var(--sp-5) var(--sp-6);
  border-color: var(--line-2);
  background: var(--paper-2);
}
body[data-app="mi-sitio"] .ms-section { margin-bottom: var(--sp-8); }
body[data-app="mi-sitio"] .ms-plantillas { gap: var(--sp-4); }
body[data-app="mi-sitio"] .ms-plantilla {
  border: 1px solid var(--line-2);
  box-shadow: var(--shadow-xs);
}
body[data-app="mi-sitio"] .ms-plantilla:hover {
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}
body[data-app="mi-sitio"] .ms-plantilla.is-active {
  border-color: var(--sky-blue);
  box-shadow: var(--focus);
}
body[data-app="mi-sitio"] .ms-testi-item { border-color: var(--line-2); }

/* ── Equipo · permissions as a calm admin list ────────────── */
body[data-app="equipo"] .eq-scroll {
  max-width: var(--page-max);
  padding: var(--sp-6) var(--pad-x) var(--sp-16);
}
body[data-app="equipo"] .bk-card--raise {
  box-shadow: none;
  border-color: var(--line-2);
}
body[data-app="equipo"] .eq-lista > .bk-card {
  border-color: var(--line-2);
  box-shadow: none;
}
body[data-app="equipo"] .eq-perm { padding: var(--sp-3) 0; }

/* ── Admin · internal console without an independent navy skin ─ */
.ac-root .ac-top {
  background: var(--paper);
  color: var(--ink);
  border-bottom: 1px solid var(--line);
}
.ac-root .ac-top__brand,
.ac-root .ac-top__back { color: var(--ink); }
.ac-root .ac-top__brand svg { opacity: 1; color: var(--sky-blue); }
.ac-root .ac-top__back {
  border: 1px solid var(--line-2);
  box-shadow: none;
  border-radius: var(--r-sm);
}
.ac-root .ac-top__back:hover {
  background: var(--paper-2);
  color: var(--ink);
}
.ac-root .ac-range {
  background: var(--paper-2);
  border: 1px solid var(--line);
}
.ac-root .ac-range__btn { color: var(--mute); }
.ac-root .ac-range__btn:hover { color: var(--ink); }
.ac-root .ac-range__btn.is-on {
  background: var(--bone);
  color: var(--ink);
  box-shadow: var(--shadow-xs);
}
.ac-root .ac-card,
.ac-root .ac-kpi,
.ac-root .ac-tablewrap { border-color: var(--line-2); }
.ac-root .ac-wrap { padding-top: var(--sp-7); }

@media (max-width: 720px) {
  body[data-app="leads"] .page-head,
  body[data-app="contratos"] #wrap,
  body[data-app="isr"] .page-scroll,
  body[data-app="finanzas"] .fin-scroll,
  body[data-app="cumplimiento"] .cp-scroll,
  .fa-wrap,
  body[data-app="video"] .vid-scroll,
  body[data-app="mi-sitio"] .ms-body,
  body[data-app="equipo"] .eq-scroll {
    padding-left: var(--sp-4);
    padding-right: var(--sp-4);
  }
  body[data-app="leads"] .kanban,
  body[data-app="leads"] .list { padding-left: var(--sp-4); padding-right: var(--sp-4); }
  body[data-app="contratos"] .card,
  body[data-app="isr"] .card { padding: var(--sp-5) !important; }
  body[data-app="finanzas"] .fin-acciones-head {
    background: transparent;
    border: 0;
    padding: 0;
  }
  .fa-wrap .fa-layout { grid-template-columns: 1fr; }
}
'''

THEME.write_text(text.rstrip() + css.rstrip() + '\n', encoding='utf-8')

TEST.write_text(r'''import unittest
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
'''.rstrip() + '\n', encoding='utf-8')

print('applied premium UX completion pass')
