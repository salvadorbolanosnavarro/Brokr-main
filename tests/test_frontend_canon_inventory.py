"""Permanent guards for automatic Canon coverage of active root HTML surfaces."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "audit.py"
QUALITY_RUNNER = ROOT / "scripts" / "run_quality.sh"


class FrontendCanonInventoryTests(unittest.TestCase):
    def test_quality_runner_is_the_single_canon_audit_entrypoint(self):
        quality = QUALITY_RUNNER.read_text(encoding="utf-8")
        audit_lines = [line.strip() for line in quality.splitlines() if line.strip().startswith("python audit.py")]
        self.assertEqual(audit_lines, ["python audit.py estadisticas.html"])

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
        for required in {
            "index.html", "whatsapp.html", "isr.html", "bandeja.html", "legal.html", "verificador.html"
        }:
            self.assertIn(required, active)


if __name__ == "__main__":
    unittest.main()
