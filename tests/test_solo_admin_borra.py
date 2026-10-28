"""En Broquer para Empresas solo el dueño o un admin borra contactos/clientes,
inmuebles y notas de bitácora (pantalla + candado en la base)."""
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class PantallaTests(unittest.TestCase):
    def test_contactos_y_clientes(self):
        for pagina, ficha in (("contactos.html", "contactos-ficha.js"), ("clientes.html", "clientes-ficha.js")):
            html = (ROOT / pagina).read_text(encoding="utf-8")
            self.assertIn("cPuedeEliminar = !org.es_empresa || org.es_admin === true;", html, pagina)
            self.assertIn("style.display = cPuedeEliminar ? 'block' : 'none';", html, pagina)
            self.assertNotIn("getElementById('btn-del').style.display = 'block';", html, pagina)
            self.assertIn("if (!editandoId || !cPuedeEliminar) return;", html, pagina)
            js = (ROOT / ficha).read_text(encoding="utf-8")
            self.assertRegex(js, r"if \(cPuedeEliminar\) items\.push\(\{ id: 'eliminar'", ficha)
            self.assertIn("if (!detContacto || !cPuedeEliminar) return;", js, ficha)

    def test_notas_de_bitacora(self):
        comun = (ROOT / "ficha-comun.js").read_text(encoding="utf-8")
        self.assertIn("function bkPuedeBorrar()", comun)
        self.assertIn("${bkPuedeBorrar() ? `<button", comun)
        for ficha in ("contactos-ficha.js", "clientes-ficha.js", "propiedades-ficha.js"):
            js = (ROOT / ficha).read_text(encoding="utf-8")
            self.assertIn("async function bkEliminarNota(id) {\n  if (!bkPuedeBorrar()) return;", js, ficha)


class BaseDeDatosTests(unittest.TestCase):
    def test_script_y_reversa(self):
        sql = (ROOT / "sql-manual" / "20261016-solo-admin-borra.sql").read_text(encoding="utf-8")
        self.assertIn("create or replace function public.soy_agente_de_empresa()", sql)
        for tabla in ("contactos", "propiedades", "actividades"):
            self.assertIn(f'create policy "solo dueno o admin borra" on public.{tabla}\n'
                          "  as restrictive for delete to public", sql)
        rev = (ROOT / "sql-manual" / "20261016-solo-admin-borra-REVERSA.sql").read_text(encoding="utf-8")
        self.assertIn("drop function if exists public.soy_agente_de_empresa()", rev)
        for tabla in ("contactos", "propiedades", "actividades"):
            self.assertIn(f'drop policy if exists "solo dueno o admin borra" on public.{tabla};', rev)


if __name__ == "__main__":
    unittest.main()
