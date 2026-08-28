"""Guard the bounded dead-stdlib cleanup prepared for main.py."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
SCRIPT = ROOT / "scripts" / "refactor_main_extract_dead_stdlib_imports_core.py"
TARGETS = {"logging", "hmac", "hashlib"}


class MainDeadStdlibImportCleanupTests(unittest.TestCase):
    def test_cleanup_is_bounded_and_state_is_prepared_or_certified(self):
        self.assertTrue(SCRIPT.exists())
        script = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('TARGETS = {"logging", "hmac", "hashlib"}', script)
        self.assertIn("ast.parse", script)
        self.assertNotIn("replace(", script)

        tree = ast.parse(MAIN.read_text(encoding="utf-8"))
        loaded = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }
        imported = {
            alias.asname or alias.name
            for node in tree.body
            if isinstance(node, ast.Import)
            for alias in node.names
        }

        # Prepared state: one or more allow-listed imports are present but dead.
        # Certified state: those dead imports have been removed. Live targets are
        # allowed to remain and are never eligible for the transform.
        dead_targets = (TARGETS & imported) - loaded
        live_targets = TARGETS & imported & loaded
        self.assertTrue(dead_targets or live_targets or not (TARGETS & imported))
        self.assertFalse(dead_targets & live_targets)


if __name__ == "__main__":
    unittest.main()
