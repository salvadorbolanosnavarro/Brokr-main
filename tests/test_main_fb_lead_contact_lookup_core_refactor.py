"""Permanent guards for Lead Ads contact Core delegation."""
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
    return "".join(lines[node.lineno - 1:node.end_lineno])


class MainFbLeadContactLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.block = _async_function_source(cls.source, "_fb_procesar_lead")

    def test_contact_lookup_patch_and_create_all_use_core(self):
        block = self.block
        self.assertNotIn("/rest/v1/contactos", block)
        self.assertIn('filas_existentes = await get_rows(\n                    "contactos",', block)
        self.assertIn('await patch_rows(\n                        "contactos",', block)
        self.assertIn('await post_rows(\n                    "contactos",', block)
        self.assertIn('accepted_statuses=(200, 201, 204)', block)

    def test_lookup_patch_and_create_error_contracts_are_preserved(self):
        block = self.block
        self.assertIn("filtro,\n                    timeout=15", block)
        self.assertIn("except httpx.HTTPStatusError:\n                filas_existentes = []", block)
        self.assertIn("existente = filas_existentes[0] if filas_existentes else None", block)
        self.assertIn('{"id": f"eq.{existente[\'id\']}"}', block)
        self.assertIn('{"es_potencial": True, "updated_at": ahora}', block)
        self.assertIn('except httpx.HTTPStatusError:\n                    pass', block)
        self.assertIn('except httpx.HTTPStatusError as e:', block)
        self.assertIn("(e.response.text or '')[:200]", block)
        self.assertIn('await _anota({"error_detail": f"Error guardando el contacto: {e}"})', block)
        compile(self.source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
