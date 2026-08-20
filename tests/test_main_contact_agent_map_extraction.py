from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "contact_import.py"


class ContactAgentMapExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.core = CORE.read_text(encoding="utf-8")

    def test_helper_lives_in_core_only(self):
        self.assertNotIn('async def _mapa_agentes_org(', self.main)
        self.assertIn('from core.contact_import import map_org_agents as _mapa_agentes_org', self.main)
        self.assertEqual(self.main.count('_mapa_agentes_org('), 2)
        self.assertIn('async def map_org_agents(', self.core)

    def test_legacy_matching_and_fail_soft_contract_is_preserved(self):
        c = self.core
        self.assertIn('"organizacion_miembros"', c)
        self.assertIn('"usuarios"', c)
        self.assertIn('except httpx.HTTPStatusError:\n            miembros = []', c)
        self.assertIn('except httpx.HTTPStatusError:\n                perfiles = []', c)
        self.assertIn('except Exception as e:', c)
        self.assertIn('No se pudo leer el mapa de agentes', c)
        self.assertIn('return {"por_email": por_email, "por_nombre": por_nombre, "_nrm": _nrm}', c)
        self.assertNotIn('/rest/v1/', c)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.core, "core/contact_import.py", "exec")


if __name__ == "__main__":
    unittest.main()
