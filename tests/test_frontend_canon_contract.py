"""Ratchet guards for Broquer's frontend Canon migration.

These tests intentionally allow only the visual debt that exists at the start
of the frontend-unification branch. As modules are migrated, the allowlists
should shrink; they must never grow.
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
        """broquer-ui.css is legacy debt isolated to WhatsApp during migration."""
        consumers = set()
        for path in ROOT.glob("*.html"):
            source = path.read_text(encoding="utf-8")
            if 'href="broquer-ui.css"' in source or "href='broquer-ui.css'" in source:
                consumers.add(path.name)

        self.assertEqual(
            consumers,
            {"whatsapp.html"},
            "broquer-ui.css must not spread beyond the existing WhatsApp migration debt",
        )

    def test_new_modules_do_not_define_another_token_root(self):
        """Only historical/marketing exceptions may carry local :root blocks."""
        allowed = {
            "landing.html",          # marketing page currently carries its b2 preview tokens
            "index.html",            # dashboard has a tiny on-navy local alpha set
            "login.html",            # auth screen is known migration debt; must be removed next
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
        """Contactos/Leads are known debt; new pages may not clone shell chrome."""
        allowed = {"contactos.html", "leads.html"}
        offenders = set()
        for path in ROOT.glob("*.html"):
            source = path.read_text(encoding="utf-8")
            if re.search(r"(?m)^\s*\.app-sidebar\s*\{", source):
                offenders.add(path.name)

        self.assertTrue(
            offenders.issubset(allowed),
            f"shell-owned sidebar CSS duplicated in: {sorted(offenders - allowed)}",
        )

    def test_module_template_points_only_to_canon(self):
        source = (ROOT / "_TEMPLATE-modulo.html").read_text(encoding="utf-8")
        self.assertIn('href="brokr-theme.css"', source)
        self.assertNotIn("broquer-ui.css", source)
        self.assertNotIn("brokr-theme-v2.css", source)

    def test_registration_screen_stays_on_canon(self):
        source = (ROOT / "registro.html").read_text(encoding="utf-8")
        self.assertIn('href="brokr-theme.css"', source)
        self.assertNotIn("Bricolage Grotesque", source)
        self.assertNotIn("Figtree", source)
        self.assertNotIn("--b2-", source)
        self.assertNotRegex(source, r"(?m)^\s*:root\s*\{")

    def test_public_invitation_screen_stays_on_canon(self):
        source = (ROOT / "unirse.html").read_text(encoding="utf-8")
        self.assertIn('href="brokr-theme.css"', source)
        self.assertNotIn("broquer-ui.css", source)
        self.assertNotIn("--b2-", source)
        self.assertNotRegex(source, r"(?m)^\s*:root\s*\{")

    def test_design_contract_names_single_executable_source(self):
        source = (ROOT / "DESIGN.md").read_text(encoding="utf-8")
        self.assertIn("`brokr-theme.css` es la implementación visual canónica", source)
        self.assertIn("No crees otra hoja de tokens", source)


if __name__ == "__main__":
    unittest.main()
