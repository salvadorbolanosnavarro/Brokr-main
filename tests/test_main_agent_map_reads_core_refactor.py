"""Keep _mapa_agentes_org's member/profile reads behind core.database."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"


class MainAgentMapReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")
        start = cls.source.index("async def _mapa_agentes_org(org_id: str, user_id: str) -> dict:")
        end = cls.source.index('@app.post("/contactos/importar-eb")', start)
        cls.block = cls.source[start:end]

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


if __name__ == "__main__":
    unittest.main()
