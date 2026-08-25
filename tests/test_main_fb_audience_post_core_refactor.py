"""Permanent guard for Facebook audience persistence through Core."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def _async_function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(
        (item for item in tree.body if isinstance(item, ast.AsyncFunctionDef) and item.name == name),
        None,
    )
    if node is None or node.end_lineno is None:
        raise AssertionError(f"async function not found: {name}")
    lines = source.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1 : node.end_lineno])


class MainFbAudiencePostCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.block = _async_function_source(cls.source, "_fb_guardar_audiencia")

    def test_audience_persistence_delegates_to_core(self):
        block = self.block
        self.assertIn('await post_rows(', block)
        self.assertIn('"fb_audiences"', block)
        self.assertIn('{"user_id": user_id, "org_id": org_id, **datos}', block)
        self.assertIn('prefer="resolution=merge-duplicates,return=minimal"', block)
        self.assertIn('timeout=10', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)
        self.assertNotIn('/rest/v1/fb_audiences', block)

    def test_legacy_fail_soft_logging_contract_stays_intact(self):
        block = self.block
        self.assertIn('except httpx.HTTPStatusError as e:', block)
        self.assertIn('_fb_tabla_falta(e.response)', block)
        self.assertIn('_fb_avisa_migracion("guardar público", e.response)', block)
        self.assertIn('e.response.status_code', block)
        self.assertIn('(e.response.text or "")[:200]', block)
        self.assertIn('except Exception as e:', block)
        self.assertIn('_fb_log.error("Error guardando el público: %s", e)', block)
        compile(self.source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
