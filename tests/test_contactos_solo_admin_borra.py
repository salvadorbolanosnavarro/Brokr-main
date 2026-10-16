"""En Broquer para Empresas solo el dueño o un admin borra contactos/clientes."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PantallaTests(unittest.TestCase):
    def test_boton_y_menu_eliminar_dependen_del_permiso(self):
        for pagina, ficha in (("contactos.html", "contactos-ficha.js"), ("clientes.html", "clientes-ficha.js")):
            html = (ROOT / pagina).read_text(encoding="utf-8")
            self.assertIn("cPuedeEliminar = !org.es_empresa || org.es_admin === true;", html, pagina)
            self.assertIn("style.display = cPuedeEliminar ? 'block' : 'none';", html, pagina)
            self.assertNotIn("getElementById('btn-del').style.display = 'block';", html, pagina)
            self.assertIn("if (!editandoId || !cPuedeEliminar) return;", html, pagina)
            js = (ROOT / ficha).read_text(encoding="utf-8")
            self.assertRegex(js, r"if \(cPuedeEliminar\) items\.push\(\{ id: 'eliminar'", ficha)
            self.assertIn("if (!detContacto || !cPuedeEliminar) return;", js, ficha)


class BaseDeDatosTests(unittest.TestCase):
    def test_script_y_reversa(self):
        sql = (ROOT / "sql-manual" / "20261016-contactos-solo-admin-borra.sql").read_text(encoding="utf-8")
        self.assertIn("create or replace function public.soy_agente_de_empresa()", sql)
        self.assertEqual(len(re.findall(r"not \(select public\.soy_agente_de_empresa\(\)\)", sql)), 2)
        self.assertIn("respaldo_contactos_borrar_20261016.politicas", sql)
        rev = (ROOT / "sql-manual" / "20261016-contactos-solo-admin-borra-REVERSA.sql").read_text(encoding="utf-8")
        self.assertIn("drop function if exists public.soy_agente_de_empresa()", rev)


if __name__ == "__main__":
    unittest.main()
