"""Ratchet guards for Broquer's frontend Canon migration.

These tests intentionally allow only the visual debt that exists at the current
frontend-unification edge. As modules are migrated, the allowlists should
shrink; they must never grow.
"""
from __future__ import annotations

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]


def strip_audit_exempt_blocks(source: str) -> str:
    """Ignore explicitly exempt self-contained artifacts such as generated PDFs."""
    return re.sub(
        r"/\* ═+ AUDIT-EXEMPT.*?/AUDIT-EXEMPT ═+ \*/",
        "",
        source,
        flags=re.S,
    )


class FrontendCanonContractTests(unittest.TestCase):
    def test_canonical_theme_is_the_only_real_theme(self):
        theme_path = ROOT / "brokr-theme.css"
        self.assertTrue(theme_path.exists())
        self.assertFalse((ROOT / "broquer-ui.css").exists(), "secondary WhatsApp stylesheet must stay deleted")

        theme = theme_path.read_text(encoding="utf-8")
        self.assertIn("BROQUER — WhatsApp domain rules · Canon", theme)
        self.assertIn('body[data-app="whatsapp"]', theme)
        self.assertIn(".w2-row--out .w2-bubble", theme)
        self.assertIn(".w2-tab.is-active", theme)

        shim = (ROOT / "brokr-theme-v2.css").read_text(encoding="utf-8")
        self.assertIn('@import url("brokr-theme.css")', shim)
        self.assertNotIn(":root", shim)

    def test_no_secondary_theme_consumers_exist(self):
        offenders = set()
        for path in ROOT.glob("*.html"):
            source = path.read_text(encoding="utf-8")
            if "broquer-ui.css" in source:
                offenders.add(path.name)
        self.assertEqual(offenders, set(), f"obsolete secondary stylesheet referenced by: {sorted(offenders)}")

        whatsapp = (ROOT / "whatsapp.html").read_text(encoding="utf-8")
        self.assertIn('href="brokr-theme.css"', whatsapp)
        self.assertNotIn("broquer-ui.css", whatsapp)

    def test_new_modules_do_not_define_another_token_root(self):
        allowed = {
            "Copia de index.html",
            "index.html",
            "mock-editorial.html",
            "mock-ejecutiva.html",
            "preview-redesign.html",
        }
        offenders = set()
        for path in ROOT.glob("*.html"):
            source = strip_audit_exempt_blocks(path.read_text(encoding="utf-8"))
            source = source.replace(':root { --safe-top: max(env(safe-area-inset-top, 0px), 44px); }', '')
            if re.search(r"(?m)^\s*:root\s*\{", source):
                offenders.add(path.name)
        self.assertTrue(offenders.issubset(allowed), f"new module-local token roots detected: {sorted(offenders - allowed)}")
        for migrated in ("isr.html", "avm.html", "contratos.html", "image-cleaner.html", "robin.html", "landing.html"):
            self.assertNotIn(migrated, offenders, f"{migrated} UI must consume Canon directly")

    def test_shell_owned_sidebar_css_exists_only_in_shell(self):
        offenders = set()
        for path in ROOT.glob("*.html"):
            source = path.read_text(encoding="utf-8")
            if re.search(r"(?m)^\s*\.app-sidebar\s*\{", source):
                offenders.add(path.name)
        self.assertEqual(offenders, set(), f"HTML pages must not own app-shell sidebar CSS: {sorted(offenders)}")

    def test_migrated_modules_use_shell_owned_chrome(self):
        for name in (
            "contactos.html", "leads.html", "isr.html", "propiedades.html",
            "avm.html", "contratos.html", "image-cleaner.html",
        ):
            source = (ROOT / name).read_text(encoding="utf-8")
            self.assertNotIn("shell-replaced-sidebar", source, name)
            self.assertNotRegex(source, r"(?m)^\s*\.app-sidebar\s*\{")
            self.assertNotIn(".app-sidebar__brand", source, name)
            self.assertIn('<script src="app-shell.js" defer></script>', source, name)

    def test_avm_and_contratos_stay_on_direct_canon_tokens(self):
        avm = (ROOT / "avm.html").read_text(encoding="utf-8")
        contratos = (ROOT / "contratos.html").read_text(encoding="utf-8")
        for source, name in ((avm, "avm.html"), (contratos, "contratos.html")):
            self.assertIn('href="brokr-theme.css"', source, name)
            self.assertNotIn("broquer-ui.css", source, name)
        self.assertNotIn('--navy: var(--sky-navy) !important;', avm)
        self.assertNotIn('--teal-glow:', avm)
        self.assertNotRegex(contratos, r"(?m)^\s*:root\s*\{")
        self.assertNotIn("var(--tealp)", contratos)

    def test_image_cleaner_stays_on_direct_canon_tokens(self):
        source = (ROOT / "image-cleaner.html").read_text(encoding="utf-8")
        self.assertIn('href="brokr-theme.css"', source)
        self.assertIn('<script src="app-shell.js" defer></script>', source)
        self.assertNotIn("broquer-ui.css", source)
        self.assertNotRegex(source, r"(?m)^\s*:root\s*\{")
        self.assertNotIn("shell-replaced-sidebar", source)
        for alias in ("--navy", "--navy2", "--teal", "--teal-dark", "--teal-bg", "--gray2", "--mut2"):
            self.assertNotIn(f"var({alias})", source)
        self.assertIn("function useInFicha()", source)
        self.assertIn("function useInFacebookAds()", source)
        self.assertIn("function useInVideo()", source)
        self.assertIn("async function downloadOne", source)

    def test_robin_demo_stays_on_canon(self):
        source = (ROOT / "robin.html").read_text(encoding="utf-8")
        self.assertIn('href="brokr-theme.css"', source)
        self.assertNotIn("fonts.googleapis.com", source)
        self.assertNotIn("Archivo", source)
        self.assertNotIn("--lona", source)
        self.assertNotRegex(source, r"(?m)^\s*:root\s*\{")
        for token in ("var(--sky-navy)", "var(--sky-blue)", "var(--line)", "var(--r-lg)"):
            self.assertIn(token, source)
        self.assertIn("box-shadow:none", source)
        self.assertIn("window.rbHecho", source)
        self.assertIn("window.rbVendido", source)
        self.assertIn("window.rbBroq", source)
        self.assertIn('id="broq-input"', source)
        self.assertIn('id="mes-monto"', source)

    def test_landing_stays_on_canon(self):
        source = (ROOT / "landing.html").read_text(encoding="utf-8")
        self.assertIn('href="brokr-theme.css"', source)
        self.assertNotIn("fonts.googleapis.com", source)
        self.assertNotIn("fonts.gstatic.com", source)
        self.assertNotRegex(source, r"(?m)^\s*:root\s*\{")
        self.assertFalse(re.search(r"--(?:b2|fs2|r2|sh2|ease2)[\w-]*", source))
        for token in (
            "var(--sky-blue)", "var(--sky-navy)", "var(--paper)", "var(--ink)",
            "var(--line)", "var(--success)", "var(--danger)", "var(--r-lg)",
        ):
            self.assertIn(token, source)
        self.assertIn("AI Real Estate Operating System", source)
        self.assertIn("login.html", source)
        self.assertIn("registro.html", source)
        self.assertIn("<video", source)

    def test_module_template_points_only_to_canon(self):
        source = (ROOT / "_TEMPLATE-modulo.html").read_text(encoding="utf-8")
        self.assertIn('href="brokr-theme.css"', source)
        self.assertNotIn("broquer-ui.css", source)
        self.assertNotIn("brokr-theme-v2.css", source)

    def assert_canon_public_screen(self, name: str):
        source = (ROOT / name).read_text(encoding="utf-8")
        self.assertIn('href="brokr-theme.css"', source, name)
        self.assertNotIn("broquer-ui.css", source, name)
        self.assertNotIn("Bricolage Grotesque", source, name)
        self.assertNotIn("Figtree", source, name)
        self.assertNotIn("--b2-", source, name)
        self.assertNotRegex(source, r"(?m)^\s*:root\s*\{")

    def test_login_screen_stays_on_canon(self):
        self.assert_canon_public_screen("login.html")

    def test_registration_screen_stays_on_canon(self):
        self.assert_canon_public_screen("registro.html")

    def test_public_invitation_screen_stays_on_canon(self):
        self.assert_canon_public_screen("unirse.html")

    def test_password_reset_screen_stays_on_canon(self):
        self.assert_canon_public_screen("reset-password.html")

    def test_public_privacy_notice_stays_on_canon(self):
        self.assert_canon_public_screen("aviso-privacidad.html")

    def test_auth_callbacks_stay_on_canon(self):
        self.assert_canon_public_screen("facebook-callback.html")
        self.assert_canon_public_screen("whatsapp-callback.html")

    def test_mail_module_stays_off_legacy_skin(self):
        source = (ROOT / "correo.html").read_text(encoding="utf-8")
        self.assertIn('href="brokr-theme.css"', source)
        self.assertNotIn("broquer-ui.css", source)
        self.assertNotIn("--bq-", source)
        self.assertNotRegex(source, r"(?m)^\s*:root\s*\{")

    def test_design_contract_names_single_executable_source(self):
        source = (ROOT / "DESIGN.md").read_text(encoding="utf-8")
        self.assertIn("`brokr-theme.css` es la implementación visual canónica", source)
        self.assertIn("No crees otra hoja de tokens", source)


if __name__ == "__main__":
    unittest.main()
