"""Permanent guards for the CRM read in /facebook/audiences/from-contacts."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "facebook_audiences.py"


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


class MainFbAudienceContactsReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.source = ROUTER.read_text(encoding="utf-8")
        cls.block = _async_function_source(cls.source, "facebook_audience_from_contacts")

    def test_contact_read_has_no_direct_supabase_rest(self):
        self.assertNotIn("/rest/v1/contactos", self.block)
        self.assertNotIn('@app.post("/facebook/audiences/from-contacts")', self.main)
        self.assertIn("from routers.facebook_audiences import router as facebook_audiences_router", self.main)

    def test_core_read_preserves_http_contract_and_meta_work(self):
        block = self.block
        self.assertIn('contactos = await get_rows("contactos", filtros, timeout=30)', block)
        self.assertIn("except httpx.HTTPStatusError:", block)
        self.assertIn('raise HTTPException(status_code=502, detail="No se pudieron leer tus contactos.")', block)
        self.assertNotIn("except Exception", block[:block.index("etiquetas_filtro")])
        self.assertIn('response = await _fb_request(', block)
        self.assertIn('await _fb_guardar_audiencia(', block)
        self.assertIn('"DELETE",', block)
        compile(self.main, "main.py", "exec")
        compile(self.source, "routers/facebook_audiences.py", "exec")


if __name__ == "__main__":
    unittest.main()
