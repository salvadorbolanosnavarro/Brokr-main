"""Guards for _mapa_agentes_org's member/profile read migration to Core."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_agent_map_reads_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("agent_map_reads_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainAgentMapReadsCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_two_direct_reads(self):
        transformed = _load_transform()(self.source)
        self.assertEqual(
            self.source.count("/rest/v1/organizacion_miembros") - transformed.count("/rest/v1/organizacion_miembros"),
            1,
        )
        self.assertEqual(
            self.source.count("/rest/v1/usuarios") - transformed.count("/rest/v1/usuarios"),
            1,
        )
        compile(transformed, "main.py", "exec")

    def test_agent_map_preserves_fail_soft_read_contract(self):
        transformed = _load_transform()(self.source)
        start = transformed.index("async def _mapa_agentes_org(org_id: str, user_id: str) -> dict:")
        end = transformed.index('@app.post("/contactos/importar-eb")', start)
        block = transformed[start:end]

        self.assertIn('miembros = await get_rows(\n                "organizacion_miembros",', block)
        self.assertIn('"org_id": f"eq.{org_id}"', block)
        self.assertIn('"select": "user_id"', block)
        self.assertIn('"limit": "200"', block)
        self.assertIn('perfiles = await get_rows(\n                    "usuarios",', block)
        self.assertIn('"id": f"in.({\',\'.join(ids)})"', block)
        self.assertIn('"select": "id,nombre,email"', block)
        self.assertEqual(block.count("timeout=15"), 2)
        self.assertEqual(block.count("except httpx.HTTPStatusError:"), 2)
        self.assertIn("except Exception as e:\n        print(f\"[importar] No se pudo leer el mapa de agentes: {e}\")", block)
        self.assertNotIn("/rest/v1/organizacion_miembros", block)
        self.assertNotIn("/rest/v1/usuarios", block)
        self.assertIn("por_email[em] = uid", block)
        self.assertIn("por_nombre[nm] = uid", block)


if __name__ == "__main__":
    unittest.main()
