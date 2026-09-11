import asyncio
from pathlib import Path
from unittest import mock
import unittest

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"
ROUTER = ROOT / "routers" / "propiedades_actualizar.py"


class _FakeRequest:
    """Duck-types the one bit of fastapi.Request this endpoint touches."""
    def __init__(self, body):
        self._body = body

    async def json(self):
        return self._body


class PropiedadesActualizarTests(unittest.TestCase):
    """Editar un inmueble ya no depende del RLS que solo dejaba escribir al
    dueño original de la fila (ver propiedades.html:sbPatchInmueble). Este
    endpoint usa la service key y decide el permiso en Python: primero
    intenta como dueño de la fila (funciona SIEMPRE, sin importar el estado
    de la membresía de organización — una versión anterior exigía org
    configurada antes que nada y dejó a cuentas sin esa membresía sin poder
    editar ni sus propios inmuebles), y solo si eso no aplica, como
    compañero activo de la misma organización.
    """

    @classmethod
    def setUpClass(cls):
        cls.main = MAIN.read_text(encoding="utf-8")
        cls.router = ROUTER.read_text(encoding="utf-8")

    def _cargar_router(self):
        import importlib
        return importlib.import_module("routers.propiedades_actualizar")

    # ── Contrato estático ────────────────────────────────────────────
    def test_route_is_registered(self):
        self.assertIn('@router.patch("/propiedades/{prop_id}")', self.router)
        self.assertIn(
            "from routers.propiedades_actualizar import router as propiedades_actualizar_router",
            self.main,
        )
        self.assertIn("app.include_router(propiedades_actualizar_router)", self.main)

    def test_owner_attempt_happens_before_any_org_lookup(self):
        r = self.router
        idx_owner = r.index('"user_id": f"eq.{user_id}"')
        idx_ctx = r.index("get_org_context(user_id)")
        self.assertLess(idx_owner, idx_ctx, "el intento como dueño debe ir antes de consultar la organización")

    def test_protected_columns_cannot_be_overwritten_from_the_body(self):
        r = self.router
        self.assertIn('_CAMPOS_PROTEGIDOS = {"id", "user_id", "org_id", "created_at"}', r)
        self.assertIn("if k not in _CAMPOS_PROTEGIDOS", r)

    def test_files_compile(self):
        compile(self.main, "main.py", "exec")
        compile(self.router, "routers/propiedades_actualizar.py", "exec")

    # ── Comportamiento real ──────────────────────────────────────────
    def test_dueno_puede_editar_sin_que_se_consulte_la_organizacion(self):
        # Esta es la regresión real: la primera versión exigía
        # get_org_context() ANTES de intentar nada, así que una cuenta sin
        # membresía de organización (o con get_org_context fallando) no
        # podía guardar cambios ni en SUS PROPIOS inmuebles.
        m = self._cargar_router()
        fila_guardada = [{"id": "p1", "estatus": "vendida"}]
        fake_patch = mock.AsyncMock(return_value=fila_guardada)
        fake_ctx = mock.AsyncMock(side_effect=AssertionError("no debía consultarse la organización"))
        with mock.patch.object(m, "get_user_id_from_token", mock.AsyncMock(return_value="u1")), \
             mock.patch.object(m, "patch_rows", fake_patch), \
             mock.patch.object(m, "get_org_context", fake_ctx):
            out = asyncio.run(m.actualizar_propiedad("p1", _FakeRequest({"estatus": "vendida"})))
        self.assertEqual(out, fila_guardada)
        fake_patch.assert_awaited_once_with(
            "propiedades", {"id": "eq.p1", "user_id": "eq.u1"}, {"estatus": "vendida"},
            prefer="return=representation", timeout=20,
        )

    def test_companero_de_organizacion_puede_editar_si_no_es_el_dueno(self):
        m = self._cargar_router()
        fila_guardada = [{"id": "p1", "estatus": "vendida"}]
        # Primer intento (como dueño) no toca nada; segundo (por org) sí.
        fake_patch = mock.AsyncMock(side_effect=[[], fila_guardada])
        fake_ctx = mock.AsyncMock(return_value={"activo": True, "org_id": "org1"})
        with mock.patch.object(m, "get_user_id_from_token", mock.AsyncMock(return_value="u2")), \
             mock.patch.object(m, "patch_rows", fake_patch), \
             mock.patch.object(m, "get_org_context", fake_ctx):
            out = asyncio.run(m.actualizar_propiedad("p1", _FakeRequest({"estatus": "vendida"})))
        self.assertEqual(out, fila_guardada)
        self.assertEqual(fake_patch.await_count, 2)
        segundo_llamado = fake_patch.await_args_list[1]
        self.assertEqual(segundo_llamado.args[1], {"id": "eq.p1", "org_id": "eq.org1"})

    def test_sin_permiso_da_404(self):
        from fastapi import HTTPException
        m = self._cargar_router()
        fake_patch = mock.AsyncMock(return_value=[])
        fake_ctx = mock.AsyncMock(return_value=None)  # sin membresía de organización
        with mock.patch.object(m, "get_user_id_from_token", mock.AsyncMock(return_value="u3")), \
             mock.patch.object(m, "patch_rows", fake_patch), \
             mock.patch.object(m, "get_org_context", fake_ctx):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(m.actualizar_propiedad("p1", _FakeRequest({"estatus": "vendida"})))
        self.assertEqual(cm.exception.status_code, 404)

    def test_organizacion_inactiva_no_habilita_el_segundo_intento(self):
        from fastapi import HTTPException
        m = self._cargar_router()
        fake_patch = mock.AsyncMock(return_value=[])
        fake_ctx = mock.AsyncMock(return_value={"activo": False, "org_id": "org1"})
        with mock.patch.object(m, "get_user_id_from_token", mock.AsyncMock(return_value="u4")), \
             mock.patch.object(m, "patch_rows", fake_patch), \
             mock.patch.object(m, "get_org_context", fake_ctx):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(m.actualizar_propiedad("p1", _FakeRequest({"estatus": "vendida"})))
        self.assertEqual(cm.exception.status_code, 404)
        fake_patch.assert_awaited_once()  # solo el intento como dueño

    def test_sin_token_da_401(self):
        from fastapi import HTTPException
        m = self._cargar_router()
        with mock.patch.object(m, "get_user_id_from_token", mock.AsyncMock(return_value=None)):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(m.actualizar_propiedad("p1", _FakeRequest({"estatus": "vendida"})))
        self.assertEqual(cm.exception.status_code, 401)

    def test_body_vacio_o_solo_campos_protegidos_da_400(self):
        from fastapi import HTTPException
        m = self._cargar_router()
        with mock.patch.object(m, "get_user_id_from_token", mock.AsyncMock(return_value="u1")):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(m.actualizar_propiedad("p1", _FakeRequest({"user_id": "otro", "id": "otro-id"})))
        self.assertEqual(cm.exception.status_code, 400)

    def test_campos_protegidos_no_llegan_a_patch_rows(self):
        m = self._cargar_router()
        fake_patch = mock.AsyncMock(return_value=[{"id": "p1"}])
        with mock.patch.object(m, "get_user_id_from_token", mock.AsyncMock(return_value="u1")), \
             mock.patch.object(m, "patch_rows", fake_patch):
            asyncio.run(m.actualizar_propiedad(
                "p1", _FakeRequest({"estatus": "vendida", "user_id": "otro", "org_id": "otro-org"}),
            ))
        cambios_enviados = fake_patch.await_args_list[0].args[2]
        self.assertEqual(cambios_enviados, {"estatus": "vendida"})


if __name__ == "__main__":
    unittest.main()
