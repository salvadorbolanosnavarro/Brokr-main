"""Expediente único: además de los documentos de ley, hasta 5 adicionales
(opcionales), que se pueden quitar; los de ley solo se reemplazan."""
from __future__ import annotations

import asyncio
from unittest import mock
import unittest

from fastapi import HTTPException

from routers import cumplimiento as c


class _R:
    headers = {}
    client = None


class DocumentosAdicionalesTests(unittest.TestCase):
    def test_tipos_validos(self):
        self.assertEqual(c._tipo_documento("ine", True), "ine")
        self.assertEqual(c._tipo_documento("adicional:  Acta de   matrimonio ", True),
                         "adicional:Acta de matrimonio")
        for malo, adicional in (("cualquiera", True), ("adicional:   ", True),
                                ("adicional:Factura", False)):
            with self.assertRaises(HTTPException):
                c._tipo_documento(malo, adicional)

    def _subir(self, existentes):
        subidos = []

        async def uid(_r):
            return "u1"

        async def get(tabla, params):
            if tabla == "pld_expedientes":
                return [{"id": "e1"}]
            return [{"tipo": t} for t in existentes]

        async def subir(u, e, tipo, archivo, quien):
            subidos.append(tipo)
            return {"tipo": tipo}

        async def nada(*a, **k):
            return {}

        with mock.patch.object(c, "_uid", uid), mock.patch.object(c, "_sb_get", get), \
             mock.patch.object(c, "_subir", subir), mock.patch.object(c, "bitacora", nada), \
             mock.patch.object(c, "_recalcular", nada):
            asyncio.run(c.subir_documento(_R(), "e1", "adicional:Factura", archivo=None))
        return subidos

    def test_hasta_cinco_adicionales(self):
        self.assertEqual(self._subir([f"adicional:D{i}" for i in range(4)]), ["adicional:Factura"])
        with self.assertRaises(HTTPException) as e:
            self._subir([f"adicional:D{i}" for i in range(5)])
        self.assertEqual(e.exception.status_code, 409)

    def test_reemplazar_uno_existente_no_cuenta_como_nuevo(self):
        existentes = [f"adicional:D{i}" for i in range(4)] + ["adicional:Factura"]
        self.assertEqual(self._subir(existentes), ["adicional:Factura"])

    def _quitar(self, tipo):
        borrados = []

        async def uid(_r):
            return "u1"

        async def get(tabla, params):
            return [{"id": "d1", "tipo": tipo, "expediente_id": "e1", "ruta": "u1/e1/x"}]

        async def borrar_obj(*a, **k):
            borrados.append("obj")

        async def borrar_fila(*a, **k):
            borrados.append("fila")

        async def nada(*a, **k):
            return None

        with mock.patch.object(c, "_uid", uid), mock.patch.object(c, "_sb_get", get), \
             mock.patch.object(c, "delete_object", borrar_obj), \
             mock.patch.object(c, "delete_rows", borrar_fila), mock.patch.object(c, "bitacora", nada):
            asyncio.run(c.quitar_documento(_R(), "d1"))
        return borrados

    def test_quitar_adicional(self):
        self.assertEqual(self._quitar("adicional:Factura"), ["obj", "fila"])

    def test_los_de_ley_no_se_quitan(self):
        with self.assertRaises(HTTPException) as e:
            self._quitar("ine")
        self.assertEqual(e.exception.status_code, 409)


if __name__ == "__main__":
    unittest.main()
