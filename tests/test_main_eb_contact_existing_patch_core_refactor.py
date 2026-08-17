"""Permanent guard for /contactos/importar-eb existing-contact PATCH Core routing."""
from __future__ import annotations

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainEbContactExistingPatchCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index('@app.post("/contactos/importar-eb")')
        end = cls.source.index('\n\n@app.post("/contactos/importar-archivo")', start)
        cls.block = cls.source[start:end]

    def test_existing_contact_patch_uses_core_with_exact_legacy_statuses(self):
        block = self.block
        self.assertIn('patch["updated_at"] = now_iso', block)
        self.assertIn('filtro_patch = ({"org_id": f"eq.{org_id_import}"} if org_id_import', block)
        self.assertIn('else {"user_id": f"eq.{user_id}"})', block)
        self.assertIn('await patch_rows(\n                            "contactos",', block)
        self.assertIn('{"id": f"eq.{existente[\'id\']}", **filtro_patch}', block)
        self.assertIn('patch,', block)
        self.assertIn('timeout=20', block)
        self.assertIn('accepted_statuses=(200, 204)', block)
        self.assertNotIn('rb = await client.patch(', block)
        self.assertNotIn('/rest/v1/contactos?id=eq.', block)

    def test_fill_only_and_counter_contract_are_preserved(self):
        block = self.block
        self.assertIn('# Rellenar solo lo que Broquer tenga vacío; nunca pisar lo del usuario', block)
        self.assertIn('if not existente.get(campo) and m.get(campo):', block)
        self.assertIn('if patch:', block)
        self.assertIn('actualizados += 1', block)
        self.assertIn('except httpx.HTTPStatusError:\n                        errores += 1', block)
        self.assertIn('else:\n                    omitidos += 1', block)


if __name__ == "__main__":
    unittest.main()
