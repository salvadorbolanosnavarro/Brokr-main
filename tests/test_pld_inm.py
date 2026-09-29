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
