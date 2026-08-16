"""Dry-run guards for /facebook/reconcile entity-ledger Core read."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_facebook_reconcile_read_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("facebook_reconcile_read_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainFacebookReconcileReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, source: str) -> str:
        start = source.index('@app.post("/facebook/reconcile")')
        end = source.index('\n\n@app.get("/facebook/page-posts")', start)
        return source[start:end]

    def test_transform_compiles_and_removes_direct_entity_get(self):
        transformed = _load_transform()(self.source)
        block = self._block(transformed)
        self.assertNotIn('r = await client.get(\n            f"{SUPABASE_URL}/rest/v1/{_FB_TABLA_ENTIDADES}"', block)
        compile(transformed, "main.py", "exec")

    def test_core_read_preserves_missing_table_and_reconcile_logic(self):
        block = self._block(_load_transform()(self.source))
        self.assertIn('filas = await get_rows(\n            _FB_TABLA_ENTIDADES,', block)
        self.assertIn('{"user_id": f"eq.{user_id}", "order": "created_at.desc", "limit": "200"}', block)
        self.assertIn('timeout=15', block)
        self.assertIn('except httpx.HTTPStatusError as e:', block)
        self.assertIn('if _fb_tabla_falta(e.response):', block)
        self.assertIn('_fb_avisa_migracion("reconciliar", e.response)', block)
        self.assertIn('status_code=503', block)
        self.assertIn('raise HTTPException(status_code=502, detail="No se pudo leer el registro de campañas.")', block)
        self.assertIn('await _fb_actualizar_entidad(row_id, {', block)
        self.assertIn('elif limpiar:', block)
        self.assertIn('rd = await _fb_request(client, "DELETE", str(cid),', block)


if __name__ == "__main__":
    unittest.main()
