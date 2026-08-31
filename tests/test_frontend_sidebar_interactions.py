from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SidebarInteractionLanguageTests(unittest.TestCase):
    def test_theme_loads_sidebar_interaction_layer(self):
        theme = (ROOT / "brokr-theme.css").read_text(encoding="utf-8")
        self.assertIn('@import url("sidebar-interactions.css");', theme)

    def test_navigation_tabs_share_blue_underline(self):
        css = (ROOT / "sidebar-interactions.css").read_text(encoding="utf-8")
        for selector in (
            'body[data-app="contactos"] .ftab.active',
            'body[data-app="leads"] .ftab.active',
            'body[data-app="tareas"] .tk-tab.active',
            'body[data-app="estadisticas"] .ftab.active',
            'body[data-app="avm"] .avm-tab.active',
            'body[data-app="facebook-ads"] .fa-tab.active',
        ):
            self.assertIn(selector, css)
        self.assertIn('border-bottom-color: var(--sky-blue) !important;', css)

    def test_segmented_controls_share_shadowed_active_pill(self):
        css = (ROOT / "sidebar-interactions.css").read_text(encoding="utf-8")
        self.assertIn('body[data-app="estadisticas"] .es-seg button.is-active', css)
        self.assertIn('body[data-app="leads"] .view-seg button.active', css)
        self.assertIn('box-shadow: var(--shadow-xs) !important;', css)

    def test_card_radio_selections_share_focus_halo(self):
        css = (ROOT / "sidebar-interactions.css").read_text(encoding="utf-8")
        self.assertIn('body[data-app="avm"] .tipo-btn.selected', css)
        self.assertIn('body[data-app="video"] .vid-fmt.is-sel', css)
        self.assertIn('box-shadow: var(--focus) !important;', css)

    def test_non_sidebar_pages_are_not_targeted(self):
        css = (ROOT / "sidebar-interactions.css").read_text(encoding="utf-8")
        for app in ("robin", "landing", "registro", "login"):
            self.assertNotIn(f'body[data-app="{app}"]', css)


if __name__ == "__main__":
    unittest.main()
