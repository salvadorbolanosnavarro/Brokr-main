"""La copia local de Contactos/Clientes es por cuenta y se borra al cerrar sesión."""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class CopiaLocalPorCuentaTests(unittest.TestCase):
    def test_llave_por_cuenta_y_sin_la_copia_compartida_vieja(self):
        for pagina, base in (("contactos.html", "brokr_contactos_cache"), ("clientes.html", "brokr_clientes_cache")):
            html = (ROOT / pagina).read_text(encoding="utf-8")
            linea = next(l for l in html.splitlines() if l.startswith("const LS_CACHE"))
            self.assertIn(f"'{base}:' + u.id", linea, pagina)
            self.assertIn(f"localStorage.removeItem('{base}')", linea, pagina)
            self.assertNotIn(f"const LS_CACHE = '{base}';", html, pagina)

    def test_cerrar_sesion_y_borrar_cuenta_limpian_las_copias(self):
        js = (ROOT / "app-shell.js").read_text(encoding="utf-8")
        self.assertIn("function limpiarCopiasLocales()", js)
        self.assertEqual(len(re.findall(r"limpiarCopiasLocales\(\);", js)), 2)


class ReglasRapidasContactosTests(unittest.TestCase):
    def test_script_y_reversa(self):
        sql = (ROOT / "sql-manual" / "20261010-contactos-reglas-rapidas.sql").read_text(encoding="utf-8")
        self.assertNotIn("using (fila_de_mi_organizacion(", sql)
        self.assertNotIn("using (contacto_en_mis_tareas(", sql)
        self.assertIn("(select auth.uid())", sql)
        self.assertIn("(select public.mi_org())", sql)
        self.assertIn("respaldo_contactos_20261010.politicas", sql)
        rev = (ROOT / "sql-manual" / "20261010-contactos-reglas-rapidas-REVERSA.sql").read_text(encoding="utf-8")
        self.assertIn("drop function if exists public.contactos_de_mis_tareas()", rev)


if __name__ == "__main__":
    unittest.main()
