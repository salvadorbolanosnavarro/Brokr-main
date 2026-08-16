"""Guards for admin_list_users' initial usuarios lookup migration to Core."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "refactor_main_admin_users_lookup_core.py"
MAIN = ROOT / "main.py"


def _load_transform():
    spec = importlib.util.spec_from_file_location("admin_users_lookup_transform", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module.transform_source


class MainAdminUsersLookupCoreRefactorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = MAIN.read_text(encoding="utf-8")

    def test_transform_compiles_and_removes_one_direct_usuarios_read(self):
        transformed = _load_transform()(self.source)
        delta = self.source.count("/rest/v1/usuarios") - transformed.count("/rest/v1/usuarios")
        self.assertIn(delta, (0, 1))
        compile(transformed, "main.py", "exec")

    def test_admin_users_lookup_preserves_error_contract_and_scope(self):
        transformed = _load_transform()(self.source)
        start = transformed.index('@app.get("/admin/users")')
        end = transformed.index('class AdminRolReq(BaseModel):', start)
        block = transformed[start:end]

        self.assertIn('users = await get_rows(\n            "usuarios",', block)
        self.assertIn('"select": "id,email,nombre,telefono,rol,activo,created_at"', block)
        self.assertIn('"order": "created_at.desc"', block)
        self.assertIn('"limit": "10000"', block)
        self.assertIn("timeout=15", block)
        self.assertIn("except httpx.HTTPStatusError as exc:", block)
        self.assertIn('raise HTTPException(status_code=500, detail=f"Error listando usuarios: {exc.response.text}")', block)
        lookup = block.split("# 2) Traer todas las suscripciones", 1)[0]
        self.assertNotIn("except Exception:", lookup)
        self.assertNotIn("/rest/v1/usuarios", lookup)
        # Subscription read remains outside this bounded cut.
        self.assertIn("/rest/v1/suscripciones", block)


if __name__ == "__main__":
    unittest.main()
