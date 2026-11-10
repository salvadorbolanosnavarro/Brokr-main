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

    def test_segmented_controls_share_approved_sky_selection(self):
        css = (ROOT / "ui/actions.css").read_text(encoding="utf-8")
        adapter = (ROOT / "ui/actions.js").read_text(encoding="utf-8")
        self.assertIn('.view-seg,.es-seg,.w2-seg', adapter)
        self.assertIn('[data-ui-kind=segment][data-ui-selected=true]', css)
        self.assertIn('background:var(--ui-sky)', css)

    def test_card_radio_selections_keep_pressed_state_and_focus(self):
        css = (ROOT / "ui/actions.css").read_text(encoding="utf-8")
        adapter = (ROOT / "ui/actions.js").read_text(encoding="utf-8")
        self.assertIn('tipo-btn|vid-fmt', adapter)
        self.assertIn('.is-sel,.is-selected,.selected', adapter)
        self.assertIn("'aria-pressed'", adapter)
        self.assertIn('outline:2px solid var(--ui-ink)', css)

    def test_non_sidebar_pages_are_not_targeted(self):
        css = (ROOT / "sidebar-interactions.css").read_text(encoding="utf-8")
        for app in ("robin", "landing", "registro", "login"):
            self.assertNotIn(f'body[data-app="{app}"]', css)


if __name__ == "__main__":
    unittest.main()
