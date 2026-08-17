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


class FrontendCanonContractTests(unittest.TestCase):
    def test_canonical_theme_is_the_only_real_theme(self):
        self.assertTrue((ROOT / "brokr-theme.css").exists())

        shim = (ROOT / "brokr-theme-v2.css").read_text(encoding="utf-8")
        self.assertIn('@import url("brokr-theme.css")', shim)
        self.assertNotIn(":root", shim)

    def test_no_new_secondary_theme_consumers(self):
        """The legacy UI skin is now isolated to WhatsApp and may not spread."""
        consumers = set()
        for path in ROOT.glob("*.html"):
            source = path.read_text(encoding="utf-8")
            if 'href="broquer-ui.css"' in source or "href='broquer-ui.css'" in source:
                consumers.add(path.name)

        self.assertEqual(
            consumers,
            {"whatsapp.html"},
            "broquer-ui.css must remain isolated to the remaining WhatsApp migration debt",
        )

    def test_new_modules_do_not_define_another_token_root(self):
        """Historical local token roots are debt; no new page may add one."""
        allowed = {
            "Copia de index.html",
            "avm.html",
            "contratos.html",
            "image-cleaner.html",
            "index.html",
            "isr.html",
            "landing.html",
            "login.html",
            "mock-editorial.html",
            "mock-ejecutiva.html",
            "preview-redesign.html",
            "robin.html",
        }
        offenders = set()
        for path in ROOT.glob("*.html"):
            source = path.read_text(encoding="utf-8")
            if re.search(r"(?m)^\s*:root\s*\{", source):
                offenders.add(path.name)

        self.assertTrue(
            offenders.issubset(allowed),
            f"new module-local token roots detected: {sorted(offenders - allowed)}",
        )

    def test_shell_owned_sidebar_css_does_not_spread(self):
        """Known duplicated shell chrome is migration debt; no new page may clone it."""
        allowed = {"contactos.html", "leads.html", "isr.html", "propiedades.html"}
        offenders = set()
        for path in ROOT.glob("*.html"):
            source = path.read_text(encoding="utf-8")
            if re.search(r"(?m)^\s*\.app-sidebar\s*\{", source):
                offenders.add(path.name)

        self.assertTrue(
            offenders.issubset(allowed),
            f"shell-owned sidebar CSS duplicated in new pages: {sorted(offenders - allowed)}",
        )

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
