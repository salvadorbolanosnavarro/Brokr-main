"""Permanent guard for Facebook lead existing-contact PATCH Core routing."""
from __future__ import annotations

import ast
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


def async_function_source(source: str, name: str) -> str:
    tree = ast.parse(source)
    node = next(
        item for item in tree.body
        if isinstance(item, ast.AsyncFunctionDef) and item.name == name
    )
    return ast.get_source_segment(source, node) or ""


class MainFbExistingContactPatchCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        cls.function = async_function_source(cls.source, "_fb_procesar_lead")
        marker = '# No se pisa lo que el agente ya escribió: solo se marca como'
        start = cls.function.index(marker)
        end_marker = '_fb_log.info("Lead %s emparejado con el contacto %s"'
        end = cls.function.index(end_marker, start)
        cls.existing_contact_block = cls.function[start:end]

    def test_existing_contact_patch_delegates_to_core(self):
        block = self.existing_contact_block
        self.assertIn('await patch_rows(', block)
        self.assertIn('"contactos"', block)
        self.assertIn('{"id": f"eq.{existente[\'id\']}"}', block)
        self.assertIn('{"es_potencial": True, "updated_at": ahora}', block)
        self.assertIn('timeout=15', block)
        self.assertNotIn('/rest/v1/contactos', block)
        self.assertNotIn('await client.patch(', block)

    def test_legacy_http_fail_soft_and_transport_behavior_stays_explicit(self):
        block = self.existing_contact_block
        self.assertIn('except httpx.HTTPStatusError:', block)
        self.assertIn('pass', block)
        patch_start = block.index('try:')
        annotate = block.index('await _anota({"procesado": True')
        patch_block = block[patch_start:annotate]
        self.assertNotIn('except Exception', patch_block)

    def test_success_annotation_contract_stays_intact(self):
        block = self.existing_contact_block
        self.assertIn('await _anota({"procesado": True, "contacto_id": existente["id"],', block)
        self.assertIn('Contacto ya existía; se marcó como potencial.', block)
        compile(self.source, "main.py", "exec")


if __name__ == "__main__":
    unittest.main()
