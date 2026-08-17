"""Permanent guards for automatic Canon coverage of active root HTML surfaces."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"
AUDIT = ROOT / "audit.py"


class FrontendCanonInventoryTests(unittest.TestCase):
    def _quality_workflow(self) -> str:
        """Use the full integration Quality workflow when present; otherwise the frontend-only production gate."""
        for name in ("quality.yml", "frontend-canon-quality.yml"):
            path = WORKFLOWS / name
            if path.exists():
                return path.read_text(encoding="utf-8")
        self.fail("A Canon Quality workflow must exist")

    def test_quality_uses_no_arg_audit_instead_of_manual_surface_list(self):
        quality = self._quality_workflow()
        self.assertIn("- name: Audit active Canon frontend inventory\n        run: python audit.py", quality)
        # A manually enumerated list can silently miss a new HTML surface.
        audit_step = quality.split("- name: Audit active Canon frontend inventory", 1)[1]
        if "- name: Report architecture debt" in audit_step:
            audit_step = audit_step.split("- name: Report architecture debt", 1)[0]
        self.assertNotIn(".html", audit_step)

    def test_no_arg_audit_excludes_only_deliberate_non_product_surfaces(self):
        tree = ast.parse(AUDIT.read_text(encoding="utf-8"))
        skip = None
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SKIP" for t in node.targets):
                skip = ast.literal_eval(node.value)
                break
        self.assertIsNotNone(skip, "audit.py must declare an explicit SKIP set")
        self.assertEqual(
            skip,
            {
                "404.html",
                "sitio.html",
                "_TEMPLATE-modulo.html",
                "Copia de index.html",
                "preview-redesign.html",
                "mock-editorial.html",
                "mock-ejecutiva.html",
            },
        )
        self.assertNotIn("legal.html", skip)
        self.assertNotIn("aviso-privacidad.html", skip)

    def test_every_non_skipped_root_html_is_in_the_automatic_inventory(self):
        source = AUDIT.read_text(encoding="utf-8")
        tree = ast.parse(source)
        skip = set()
        for node in tree.body:
            if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SKIP" for t in node.targets):
                skip = ast.literal_eval(node.value)
                break
        active = {path.name for path in ROOT.glob("*.html")} - skip
        self.assertGreaterEqual(len(active), 42)
        # These are the two master references and the four last migrated outliers.
        for required in {
            "index.html", "whatsapp.html", "isr.html", "bandeja.html", "legal.html", "verificador.html"
        }:
            self.assertIn(required, active)


if __name__ == "__main__":
    unittest.main()
