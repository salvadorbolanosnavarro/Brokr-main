"""El catálogo de inmuebles del frontend debe estar generado desde el de Python."""
from __future__ import annotations

import json
from pathlib import Path
import unittest

from core.catalogo_inmuebles import (
    CARACTERISTICAS,
    EB_TIPOS,
    TIPO_KEYS,
    catalogo_dict,
    clasificar_amenidades,
    tipo_familia,
)

ROOT = Path(__file__).resolve().parents[1]


class CatalogoInmueblesTests(unittest.TestCase):
    def test_js_generado_esta_sincronizado(self):
        js = (ROOT / "inmuebles-catalogo.js").read_text(encoding="utf-8")
        ini, fin = "/*__CATALOGO_INICIO__*/", "/*__CATALOGO_FIN__*/"
        data = json.loads(js[js.index(ini) + len(ini):js.index(fin)])
        self.assertEqual(
            data, json.loads(json.dumps(catalogo_dict(), ensure_ascii=False)),
            "Corre: python scripts/gen_catalogo_inmuebles.py",
        )

    def test_claves_unicas_y_familias_validas(self):
        claves = [c["key"] for g in CARACTERISTICAS for c in g["items"]]
        self.assertEqual(len(claves), len(set(claves)))
        for k in TIPO_KEYS:
            self.assertIn(tipo_familia(k), {"casa", "departamento", "terreno", "local", "oficina", "bodega", "otro"})
        for v in EB_TIPOS.values():
            self.assertIn(v, TIPO_KEYS)

    def test_clasificar_amenidades_ignora_acentos_y_mayusculas(self):
        claves, otras = clasificar_amenidades(["ALBERCA", "jardin", "Vista a la presa", "alberca"])
        self.assertEqual(claves, ["alberca", "jardin"])
        self.assertEqual(otras, ["Vista a la presa"])


if __name__ == "__main__":
    unittest.main()
