"""Permanent guards for /facebook/reconcile entity-ledger Core read."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def _async_function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(
        (
            item
            for item in tree.body
            if isinstance(item, ast.AsyncFunctionDef) and item.name == name
        ),
        None,
    )
    if node is None or node.end_lineno is None:
        raise AssertionError(f"async function not found: {name}")
    lines = source.splitlines(keepends=True)
    return "".join(lines[node.lineno - 1 : node.end_lineno])


class MainFacebookReconcileReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.block = _async_function_source(cls.source, "facebook_reconcile")

    def test_direct_entity_get_stays_removed(self):
        self.assertNotIn(
            'r = await client.get(\n            f"{SUPABASE_URL}/rest/v1/{_FB_TABLA_ENTIDADES}"',
            self.block,
        )

    def test_core_read_preserves_missing_table_and_reconcile_logic(self):
        block = self.block
        self.assertIn('filas = await get_rows(\n            _FB_TABLA_ENTIDADES,', block)
        self.assertIn(
            '{"user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "200"}',
            block,
        )
        self.assertIn('timeout=15', block)
        self.assertIn('except httpx.HTTPStatusError as e:', block)
        self.assertIn('if _fb_tabla_falta(e.response):', block)
        self.assertIn('_fb_avisa_migracion("reconciliar", e.response)', block)
        self.assertIn('status_code=503', block)
        self.assertIn(
            'raise HTTPException(status_code=502, detail="No se pudo leer el registro de campañas.")',
            block,
        )
        self.assertIn('await _fb_actualizar_entidad(row_id, {', block)
        self.assertIn('elif limpiar:', block)
        self.assertIn('rd = await _fb_request(client, "DELETE", str(cid),', block)
        compile(self.source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
