"""Keep shared contact-import agent mapping behind core.database."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
CORE = ROOT / "core" / "contact_import.py"
ROUTER = ROOT / "routers" / "easybroker_contact_import.py"
FILE_ROUTER = ROOT / "routers" / "contact_file_import.py"


class MainAgentMapReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.block = CORE.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")
        cls.file_router = FILE_ROUTER.read_text(encoding="utf-8")

    def test_agent_map_reads_use_core(self):
        block = self.block
        self.assertIn('miembros = await get_rows(\n                "organizacion_miembros",', block)
        self.assertIn('"org_id": f"eq.{org_id}"', block)
        self.assertIn('"select": "user_id"', block)
        self.assertIn('"limit": "200"', block)
        self.assertIn('perfiles = await get_rows(\n                    "usuarios",', block)
        self.assertIn('"id": f"in.({\',\'.join(ids)})"', block)
        self.assertIn('"select": "id,nombre,email"', block)
        self.assertEqual(block.count("timeout=15"), 2)

    def test_agent_map_keeps_fail_soft_contract_and_no_direct_rest(self):
        block = self.block
        self.assertEqual(block.count("except httpx.HTTPStatusError:"), 2)
        self.assertIn("except Exception as e:\n        print(f\"[importar] No se pudo leer el mapa de agentes: {e}\")", block)
        self.assertNotIn("/rest/v1/organizacion_miembros", block)
        self.assertNotIn("/rest/v1/usuarios", block)
        self.assertNotIn("Authorization", block)
        self.assertIn("por_email[em] = uid", block)
        self.assertIn("por_nombre[nm] = uid", block)

    def test_both_importers_delegate_to_shared_core_helper(self):
        self.assertNotIn("async def _mapa_agentes_org(", self.main)
        self.assertIn("from core.contact_import import map_org_agents as _mapa_agentes_org", self.main)
        if '@app.post("/contactos/importar-archivo")' in self.main:
            self.assertEqual(self.main.count("_mapa_agentes_org("), 1)
        else:
            self.assertEqual(self.main.count("_mapa_agentes_org("), 0)
            self.assertIn('"_mapa_agentes_org": _mapa_agentes_org', self.main)
            self.assertEqual(self.file_router.count("_mapa_agentes_org("), 1)
        self.assertIn("from core.contact_import import map_org_agents", self.router)
        self.assertEqual(self.router.count("map_org_agents("), 1)


if __name__ == "__main__":
    unittest.main()
