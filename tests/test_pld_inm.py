"""Aviso de inmuebles (fracción V): el XML que genera Broquer debe pasar el
XSD oficial de la UIF (core/pld/inm.xsd) y, si faltan datos, decir cuáles."""
from __future__ import annotations

from pathlib import Path
import unittest

from core import pld_inm

ROOT = Path(__file__).resolve().parents[1]

CFG = {"rfc_sujeto_obligado": "gomj800101ab1"}

EXP_FISICA = {
    "id": "e1", "tipo_persona": "fisica", "nombre": "José María", "apellido_paterno": "Núñez",
    "apellido_materno": "", "fecha_nacimiento": "1980-05-17", "rfc": "NUMJ800517AB1",
    "curp": "NUMJ800517HMNXXX09", "nacionalidad": "Mexicana", "actividad_economica": "1110100",
    "telefono": "443 123 4567", "email": "jose@correo.com",
    "dom_calle": "Av. Madero Pte.", "dom_num_ext": "1234", "dom_colonia": "Centro",
    "dom_cp": "58000", "bc_es_el_mismo": True,
}
EXP_MORAL = {
    "id": "e2", "tipo_persona": "moral", "razon_social": "Inmobiliaria Ñandú, S.A. de C.V.",
    "fecha_constitucion": "2010-01-01", "rfc_moral": "INA100101AB1", "nacionalidad": "MX",
    "giro_mercantil": "1100001", "rep_nombre": "Ana", "rep_apellido_paterno": "López",
    "rep_rfc": "LOAA800101AB1", "dom_calle": "Reforma", "dom_num_ext": "10",
    "dom_colonia": "Juárez", "dom_cp": "06600", "bc_es_el_mismo": False,
    "bc_nombre": "Pedro", "bc_apellido_paterno": "Ruiz", "bc_fecha_nacimiento": "1970-02-02",
}


def _op(**kw):
    op = {
        "id": "4f1c2b9e-1234-4abc-9def-000000000001", "expediente_id": "e1",
        "tipo_operacion": "compraventa", "fecha_operacion": "2026-09-12", "monto": 2400000,
        "inusual": False,
        "aviso_datos": {
            "figura_cliente": "2", "figura_so": "3",
            "contrapartes": [{"tipo_persona": "fisica", "nombre": "Luis", "apellido_paterno": "Pérez",
                              "apellido_materno": "Gómez", "nacionalidad": "MX"}],
            "inmueble": {"tipo_inmueble": "1", "valor_pactado": 2400000, "calle": "Cipres",
                         "numero_exterior": "167", "colonia": "Melchor Ocampo",
                         "codigo_postal": "58070", "dimension_terreno": 160,
                         "dimension_construido": 210.5, "folio_real": "00123-A"},
            "instrumento": {"tipo": "publico", "numero": "4521", "fecha": "2026-09-12",
                            "notario": "123", "entidad": "16", "avaluo_catastral": 1500000},
            "liquidaciones": [{"fecha_pago": "2026-09-12", "forma_pago": "4",
                               "instrumento_monetario": "8", "moneda": "1", "monto": 2400000}],
        },
    }
    op.update(kw)
    return op


class AvisoInmTests(unittest.TestCase):
    def test_el_ejemplo_oficial_pasa_el_xsd(self):
        xml = (ROOT / "tests/golden/ejemplo_inm_oficial.xml").read_text(encoding="utf-8")
        self.assertEqual(pld_inm.validar_xsd(xml.split("?>", 1)[1]), [])

    def test_aviso_completo_persona_fisica_pasa_el_xsd(self):
        xml, problemas = pld_inm.construir_xml(CFG, "2026-09", [_op()], {"e1": EXP_FISICA})
        self.assertEqual(problemas, [])
        self.assertEqual(pld_inm.validar_xsd(xml), [])
        self.assertIn("<tipo_operacion>501</tipo_operacion>", xml)
        self.assertIn("<nombre>JOSE MARIA</nombre>", xml)
        self.assertIn("<apellido_paterno>NUÑEZ</apellido_paterno>", xml)
        self.assertIn("<apellido_materno>XXXX</apellido_materno>", xml)
        self.assertIn("<clave_sujeto_obligado>GOMJ800101AB1</clave_sujeto_obligado>", xml)
        self.assertIn("<mes_reportado>202609</mes_reportado>", xml)

    def test_persona_moral_con_beneficiario_y_contrato_privado_pasa_el_xsd(self):
        op = _op(expediente_id="e2", inusual=True, inusual_motivo="Pago de un tercero")
        op["aviso_datos"]["instrumento"] = {"tipo": "contrato", "fecha_contrato": "2026-09-01"}
        op["aviso_datos"]["tipo_alerta"] = "3102"
        xml, problemas = pld_inm.construir_xml(CFG, "2026-09", [op], {"e2": EXP_MORAL})
        self.assertEqual(problemas, [])
        self.assertEqual(pld_inm.validar_xsd(xml), [])
        self.assertIn("<prioridad>2</prioridad>", xml)
        self.assertIn("<dueno_beneficiario>", xml)

    def test_informe_en_ceros_pasa_el_xsd(self):
        xml, problemas = pld_inm.construir_xml(CFG, "2026-09", [], {})
        self.assertEqual(problemas, [])
        self.assertEqual(pld_inm.validar_xsd(xml), [])

    def test_faltantes_se_reportan_en_espanol(self):
        op = _op()
        op["aviso_datos"] = {}
        _, problemas = pld_inm.construir_xml({}, "2026-09", [op], {"e1": dict(EXP_FISICA, actividad_economica="")})
        texto = " ".join(problemas)
        for esperado in ("RFC con homoclave como sujeto obligado", "comprador o vendedor",
                         "tipo de inmueble", "código postal del inmueble", "número de escritura",
                         "otra parte", "actividad económica"):
            self.assertIn(esperado, texto)

    def test_arrendamiento_no_va_en_aviso_de_inmuebles(self):
        _, problemas = pld_inm.construir_xml(CFG, "2026-09", [_op(tipo_operacion="arrendamiento")],
                                             {"e1": EXP_FISICA})
        self.assertIn("fracción XV", " ".join(problemas))

    def test_inusual_no_puede_ir_sin_alerta(self):
        op = _op(inusual=True)
        op["aviso_datos"]["tipo_alerta"] = "100"
        _, problemas = pld_inm.construir_xml(CFG, "2026-09", [op], {"e1": EXP_FISICA})
        self.assertIn("Sin alerta", " ".join(problemas))

    def test_catalogos_oficiales(self):
        c = pld_inm.catalogos()
        self.assertEqual(c["tipo_operacion"], [["501", "Compra Venta de Inmuebles"]])
        self.assertEqual({k for k, _ in c["figura_so"]}, {"1", "2", "3"})
        self.assertEqual(len(c["entidad_federativa"]), 32)
        self.assertIn(["1000000", "NO APLICA"], c["actividad_economica"])


if __name__ == "__main__":
    unittest.main()


class ModificatorioXmlTests(unittest.TestCase):
    def test_modificatorio_pasa_el_xsd(self):
        op = _op(_modificatorio={"folio": "2026-1234", "descripcion": "Se corrige el código postal"})
        xml, problemas = pld_inm.construir_xml(CFG, "2026-09", [op], {"e1": EXP_FISICA})
        self.assertEqual(problemas, [])
        self.assertEqual(pld_inm.validar_xsd(xml), [])
        self.assertIn("<folio_modificacion>2026-1234</folio_modificacion>", xml)
        self.assertIn("SE CORRIGE EL CODIGO POSTAL", xml)

    def test_modificatorio_sin_folio_valido_se_reporta(self):
        op = _op(_modificatorio={"folio": "1234", "descripcion": "x"})
        _, problemas = pld_inm.construir_xml(CFG, "2026-09", [op], {"e1": EXP_FISICA})
        self.assertIn("folio del aviso original", " ".join(problemas))


class CicloAvisoTests(unittest.TestCase):
    """Endpoints del ciclo con la base de datos simulada."""

    def _correr(self, fn, aviso, *args, ops=None):
        import asyncio
        from unittest import mock
        from routers import cumplimiento as c
        self.patches = []
        self.posts = []

        async def uid(_r):
            return "u1"

        async def cfg(_u):
            return dict(CFG)

        async def get(tabla, params):
            if tabla == "pld_avisos":
                return [aviso] if aviso else []
            if tabla == "pld_operaciones":
                return ops if ops is not None else [{"id": "o1", "inusual": False}]
            if tabla == "pld_expedientes":
                return [EXP_FISICA]
            return []

        async def patch(tabla, params, payload):
            self.patches.append((tabla, params, payload))
            return [{"id": "o1"}] if tabla == "pld_operaciones" else [aviso]

        async def post(tabla, payload):
            self.posts.append((tabla, payload))
            return [dict(payload, id="nuevo")]

        async def bit(*a, **k):
            return None

        async def subir(*a, **k):
            return None

        class R:
            headers = {}
            client = None

        with mock.patch.object(c, "_uid", uid), mock.patch.object(c, "_config", cfg), \
             mock.patch.object(c, "_sb_get", get), mock.patch.object(c, "_sb_patch", patch), \
             mock.patch.object(c, "_sb_post", post), mock.patch.object(c, "bitacora", bit), \
             mock.patch.object(c, "upload_object", subir):
            return asyncio.run(getattr(c, fn)(R(), "a1", *args))

    def test_rehacer_libera_operaciones(self):
        r = self._correr("descartar_aviso", {"id": "a1", "estatus": "generado", "periodo": "2026-09"})
        self.assertEqual(r["operaciones_liberadas"], 1)
        self.assertEqual(self.patches[0][2]["aviso_id"], None)
        self.assertEqual(self.patches[1][2]["estatus"], "descartado")

    def test_rehacer_un_aceptado_no_se_permite(self):
        from fastapi import HTTPException
        with self.assertRaises(HTTPException) as e:
            self._correr("descartar_aviso", {"id": "a1", "estatus": "presentado"})
        self.assertEqual(e.exception.status_code, 409)

    def test_ya_lo_subi(self):
        self._correr("marcar_subido", {"id": "a1", "estatus": "generado"})
        self.assertEqual(self.patches[0][2]["estatus"], "subido")
        self.assertIn("subido_at", self.patches[0][2])

    def test_rechazo_libera_y_guarda_motivo(self):
        from routers import cumplimiento as c
        r = self._correr("marcar_rechazado", {"id": "a1", "estatus": "subido", "periodo": "2026-09"},
                         c.RechazoIn(motivo="CP inexistente"))
        self.assertEqual(r["operaciones_liberadas"], 1)
        final = self.patches[-1][2]
        self.assertEqual((final["estatus"], final["motivo_rechazo"]), ("rechazado", "CP inexistente"))

    def test_acuse_guarda_folio_de_la_operacion(self):
        from routers import cumplimiento as c
        self._correr("marcar_presentado", {"id": "a1", "estatus": "subido"},
                     c.PresentadoIn(acuse_folio="2026-77"), ops=[{"id": "o1", "inusual": True}])
        op_patch = [p for p in self.patches if p[0] == "pld_operaciones"][0][2]
        self.assertEqual(op_patch["folio_uif"], "2026-77")
        self.assertIn("inusual_reportada_at", op_patch)

    def test_modificatorio_valido(self):
        from datetime import datetime, timezone
        from routers import cumplimiento as c
        op = _op(aviso_id="a1", folio_uif="2026-77")
        r = self._correr("generar_modificatorio",
                         {"id": "a1", "estatus": "presentado", "periodo": "2026-09", "referencia": "R",
                          "presentado_at": datetime.now(timezone.utc).isoformat()},
                         c.ModificatorioIn(operacion_id=op["id"], descripcion="Se corrige el CP"), ops=[op])
        self.assertTrue(r["validado"])
        self.assertIn("<folio_modificacion>2026-77</folio_modificacion>", r["xml"])
        self.assertEqual(self.posts[0][1]["tipo"], "modificatorio")

    def test_modificatorio_fuera_de_30_dias(self):
        from fastapi import HTTPException
        from routers import cumplimiento as c
        with self.assertRaises(HTTPException) as e:
            self._correr("generar_modificatorio",
                         {"id": "a1", "estatus": "presentado", "presentado_at": "2026-01-01T00:00:00+00:00"},
                         c.ModificatorioIn(operacion_id="x", descripcion="y"))
        self.assertEqual(e.exception.status_code, 409)


class AlertasTests(unittest.TestCase):
    def _alertas(self, **kw):
        from datetime import date
        from core.pld_alertas import alertas_pld
        from routers.cumplimiento import fecha_limite
        base = dict(cfg={"dias_aviso_previo": 7}, hoy=date(2026, 10, 12), pendientes=[], avisos=[], inusuales=[])
        base.update(kw)
        return alertas_pld(base["cfg"], base["hoy"], base["pendientes"], base["avisos"],
                           base["inusuales"], fecha_limite)

    def test_periodo_pendiente_cerca_de_la_fecha_limite_es_urgente(self):
        a = self._alertas(pendientes=[{"fecha_operacion": "2026-09-12"}])[0]
        self.assertEqual((a["nivel"], a["push"]), ("urgente", True))
        self.assertIn("septiembre 2026", a["titulo"])
        self.assertIn("vence en 5 días", a["titulo"])

    def test_formato_anterior_pide_rehacer(self):
        a = self._alertas(avisos=[{"id": "v", "estatus": "generado", "periodo": "2026-09"}])[0]
        self.assertIn("formato anterior", a["titulo"])

    def test_por_subir_y_en_revision(self):
        al = self._alertas(avisos=[
            {"id": "1", "estatus": "generado", "formato": "INM", "periodo": "2026-09"},
            {"id": "2", "estatus": "subido", "formato": "INM", "periodo": "2026-08",
             "subido_at": "2026-10-01T10:00:00+00:00"}])
        titulos = " | ".join(a["titulo"] for a in al)
        self.assertIn("Sube tu aviso de septiembre 2026", titulos)
        self.assertIn("Revisa en el portal del SAT", titulos)
        self.assertTrue(all(a["push"] for a in al))

    def test_aceptado_y_descartado_no_alertan(self):
        self.assertEqual(self._alertas(avisos=[{"id": "1", "estatus": "presentado"},
                                               {"id": "2", "estatus": "descartado"}]), [])


class PushAlertasTests(unittest.TestCase):
    def test_manda_una_vez_al_dia_y_en_horario(self):
        import asyncio, sys, types
        from datetime import datetime, timezone
        from unittest import mock
        from routers import cumplimiento as c
        enviados, guardado = [], {}

        async def push(uid, titulo, cuerpo, datos=None):
            enviados.append(titulo)
            return True
        falso = types.ModuleType("push")
        falso.enviar_push = push

        async def get(tabla, params):
            if tabla == "pld_config":
                return [{"user_id": "u1", "dias_aviso_previo": 7, "alertas_enviadas": dict(guardado)}]
            if tabla == "pld_operaciones" and "genera_aviso" in params:
                return [{"id": "o1", "fecha_operacion": "2026-09-12"}]
            return []

        async def patch(tabla, params, payload):
            guardado.clear()
            guardado.update(payload["alertas_enviadas"])
            return []

        with mock.patch.dict(sys.modules, {"push": falso}), \
             mock.patch.object(c, "_sb_get", get), mock.patch.object(c, "_sb_patch", patch):
            mediodia = datetime(2026, 10, 12, 18, 0, tzinfo=timezone.utc)   # 12:00 en CDMX
            self.assertEqual(asyncio.run(c.revisar_alertas_pld(mediodia)), 1)
            self.assertEqual(asyncio.run(c.revisar_alertas_pld(mediodia)), 0)   # ya se mandó hoy
            madrugada = datetime(2026, 10, 13, 8, 0, tzinfo=timezone.utc)   # 2:00 en CDMX
            self.assertEqual(asyncio.run(c.revisar_alertas_pld(madrugada)), 0)
