from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "propiedades_actualizar.py"


class PropiedadesActualizarTests(unittest.TestCase):
    """Editar un inmueble ya no depende del RLS que solo dejaba escribir al
    dueño original de la fila (ver propiedades.html:sbPatchInmueble). Este
    endpoint usa la service key y valida "misma organización" en Python,
    igual que ya hace /propiedades/eliminar-masivo para borrar.
    """

    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def test_route_is_registered(self):
        self.assertIn('@router.patch("/propiedades/{prop_id}")', self.router)
        self.assertIn(
            "from routers.propiedades_actualizar import router as propiedades_actualizar_router",
            self.main,
        )
        self.assertIn("app.include_router(propiedades_actualizar_router)", self.main)

    def test_requires_authenticated_active_org_member(self):
        r = self.router
        self.assertIn("user_id = await get_user_id_from_token(request)", r)
        self.assertIn("status_code=401", r)
        self.assertIn('ctx = await get_org_context(user_id)', r)
        self.assertIn('not ctx.get("org_id") or not ctx.get("activo")', r)
        self.assertIn("status_code=403", r)

    def test_scopes_write_to_the_caller_org_and_property_id(self):
        r = self.router
        self.assertIn('"propiedades"', r)
        self.assertIn('{"id": f"eq.{prop_id}", "org_id": f"eq.{ctx[\'org_id\']}"}', r)
        self.assertIn("await patch_rows(", r)

    def test_protected_columns_cannot_be_overwritten_from_the_body(self):
        r = self.router
        self.assertIn('_CAMPOS_PROTEGIDOS = {"id", "user_id", "org_id", "created_at"}', r)
        self.assertIn("if k not in _CAMPOS_PROTEGIDOS", r)

    def test_zero_rows_surfaces_a_clear_error_instead_of_a_silent_no_op(self):
        r = self.router
        self.assertIn("if not filas:", r)
        self.assertIn("status_code=404", r)
        self.assertIn("no tienes permiso sobre este registro o ya no existe", r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/propiedades_actualizar.py", "exec")


if __name__ == "__main__":
    unittest.main()
