"""Dry-run guards for the CRM read in /facebook/audiences/from-contacts."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_fb_audience_contacts_read_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("fb_audience_contacts_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainFbAudienceContactsReadCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, source: str) -> str:
        start = source.index('@app.post("/facebook/audiences/from-contacts")')
        end = source.index("\n\nclass FbLookalikeRequest", start)
        return source[start:end]

    def test_transform_compiles_and_removes_direct_contact_read(self):
        transformed = _load_transform()(self.source)
        block = self._block(transformed)
        self.assertNotIn("/rest/v1/contactos", block)
        compile(transformed, "main.py", "exec")

    def test_core_read_preserves_http_contract_and_meta_work(self):
        transformed = _load_transform()(self.source)
        block = self._block(transformed)
        self.assertIn('contactos = await get_rows(\n            "contactos",', block)
        self.assertIn("filtros,\n            timeout=30", block)
        self.assertIn("except httpx.HTTPStatusError:", block)
        self.assertIn('raise HTTPException(status_code=502, detail="No se pudieron leer tus contactos.")', block)
        self.assertNotIn("except Exception", block[:block.index("etiquetas_filtro")])
        self.assertIn('r_aud = await _fb_request(', block)
        self.assertIn('await _fb_guardar_audiencia(user_id, org_id, {', block)
        self.assertIn('await _fb_request(client, "DELETE", audience_id', block)


if __name__ == "__main__":
    unittest.main()
