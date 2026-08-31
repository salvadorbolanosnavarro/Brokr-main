from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SidebarCompositionTests(unittest.TestCase):
    def test_statistics_uses_shared_sidebar_composition_layer(self):
        shim = (ROOT / "brokr-theme-v2.css").read_text(encoding="utf-8")
        self.assertIn('@import url("brokr-theme.css")', shim)
        self.assertIn('@import url("sidebar-unification.css")', shim)

    def test_statistics_standalone_hero_is_visually_flattened(self):
        css = (ROOT / "sidebar-unification.css").read_text(encoding="utf-8")
        self.assertIn('body[data-app="estadisticas"] .es-hero', css)
        self.assertIn('background: var(--paper) !important', css)
        self.assertIn('position: static !important', css)

    def test_statistics_selection_semantics_match_whatsapp(self):
        css = (ROOT / "sidebar-unification.css").read_text(encoding="utf-8")
        whatsapp = (ROOT / "whatsapp.html").read_text(encoding="utf-8")
        # Segmented controls: active option is a raised pill.
        self.assertIn('.w2-seg button.is-on{ background:var(--canvas); color:var(--ink); box-shadow:var(--shadow-xs); }', whatsapp)
        self.assertIn('body[data-app="estadisticas"] .es-seg button.is-active', css)
        self.assertIn('box-shadow: var(--shadow-xs) !important', css)
        # Navigation tabs: active option is an underline, not a raised pill.
        self.assertIn('.w2-tab.is-active{ color:var(--ink); border-bottom-color:var(--sky-blue); }', whatsapp)
        self.assertIn('body[data-app="estadisticas"] .ftab.active', css)
        self.assertIn('border-bottom-color: var(--sky-blue) !important', css)

    def test_sidebar_layer_does_not_target_non_sidebar_pages(self):
        css = (ROOT / "sidebar-unification.css").read_text(encoding="utf-8")
        self.assertNotIn('body[data-app="robin"]', css)
        self.assertNotIn('body[data-app="landing"]', css)
        self.assertNotIn('body[data-app="registro"]', css)


if __name__ == "__main__":
    unittest.main()
