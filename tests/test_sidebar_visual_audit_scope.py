from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SidebarVisualAuditScopeTests(unittest.TestCase):
    def test_audit_scope_explicitly_excludes_non_sidebar_surfaces(self):
        audit = (ROOT / "SIDEBAR_VISUAL_AUDIT.md").read_text(encoding="utf-8")
        self.assertIn("non-sidebar pages out of scope", audit)
        self.assertNotIn("robin.html`:", audit)

    def test_transform_targets_only_first_cut_sidebar_modules(self):
        src = (ROOT / "scripts" / "refactor_frontend_sidebar_composition.py").read_text(encoding="utf-8")
        for name in ["propiedades.html", "contactos.html", "tareas.html", "leads.html", "avm.html"]:
            self.assertIn(f'"{name}"', src)
        for name in ["robin.html", "landing.html", "registro.html"]:
            self.assertNotIn(f'"{name}"', src)


if __name__ == "__main__":
    unittest.main()
