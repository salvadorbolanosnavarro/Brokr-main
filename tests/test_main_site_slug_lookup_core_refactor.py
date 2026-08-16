"""Guards for public site slug usuarios lookup migration to Core."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_site_slug_lookup_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("site_slug_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainSiteSlugLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_one_direct_usuarios_read(self):
        transformed = _load_transform()(self.source)
        delta = self.source.count("/rest/v1/usuarios") - transformed.count("/rest/v1/usuarios")
        self.assertIn(delta, (0, 1))
        compile(transformed, "main.py", "exec")

    def test_slug_lookup_preserves_http_empty_404_and_lead_writes(self):
        transformed = _load_transform()(self.source)
        start = transformed.index('@app.post("/sitio/{slug}/lead")')
        block = transformed[start:]

        self.assertIn('rows = await get_rows(\n                "usuarios",', block)
        self.assertIn('"slug": f"eq.{slug}"', block)
        self.assertIn('"sitio_activo": "eq.true"', block)
        self.assertIn('"select": "id"', block)
        self.assertIn('"limit": "1"', block)
        self.assertIn("timeout=10", block)
        self.assertIn("except httpx.HTTPStatusError:\n            rows = []", block)
        self.assertIn('raise HTTPException(status_code=404, detail="Sitio no encontrado")', block)
        self.assertIn('user_id = rows[0]["id"]', block)
        lookup = block.split("# 2) Dedup", 1)[0]
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/usuarios", lookup)
        # Contact dedupe/create writes stay in the legacy client for this read-only cut.
        self.assertIn("/rest/v1/contactos", block)


if __name__ == "__main__":
    unittest.main()
