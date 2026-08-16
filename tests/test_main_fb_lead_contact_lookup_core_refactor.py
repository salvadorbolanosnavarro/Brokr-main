"""Dry-run guards for Lead Ads contact-dedup Core migration."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_fb_lead_contact_lookup_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("fb_lead_contact_lookup_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainFbLeadContactLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def _block(self, source: str) -> str:
        start = source.index("async def _fb_procesar_lead(valor: dict) -> None:")
        end = source.index('\n\n@app.post("/facebook/leadgen/subscribe")', start)
        return source[start:end]

    def test_transform_compiles_and_leaves_only_contact_writes_direct(self):
        transformed = _load_transform()(self.source)
        block = self._block(transformed)
        self.assertEqual(block.count("/rest/v1/contactos"), 2)
        compile(transformed, "main.py", "exec")

    def test_lookup_uses_core_and_preserves_patch_post(self):
        block = self._block(_load_transform()(self.source))
        self.assertIn('filas_existentes = await get_rows(\n                    "contactos",', block)
        self.assertIn("filtro,\n                    timeout=15", block)
        self.assertIn("except httpx.HTTPStatusError:\n                filas_existentes = []", block)
        self.assertIn("existente = filas_existentes[0] if filas_existentes else None", block)
        self.assertIn('await client.patch(\n                    f"{SUPABASE_URL}/rest/v1/contactos"', block)
        self.assertIn('rc = await client.post(\n                f"{SUPABASE_URL}/rest/v1/contactos"', block)
        self.assertIn('await _anota({"error_detail": f"Error guardando el contacto: {e}"})', block)


if __name__ == "__main__":
    unittest.main()
