import asyncio
import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from routers import seguimiento_api as api
from routers import seguimiento_datos as datos
from routers import seguimiento_motor as motor
from routers.seguimiento_calientes import puntuar
from routers.seguimiento_eventos import precio_de, precio_texto, titulo_de
from routers.seguimiento_schema import (PasoReq, SecuenciaReq, clasificar_error, en_horario, primer_nombre,
                                        programar, render_variables, limpiar_secuencia)


UTC = timezone.utc


class ReglasPuras(unittest.TestCase):
    def test_secuencia_valida_y_normalizada(self):
        s = limpiar_secuencia(SecuenciaReq(nombre="  Leads portal ", numero_id="n1", hora_envio=3,
                                           pasos=[PasoReq(dias=99, plantilla="Seg Primer-Contacto", variables=["{nombre}"])]))
        self.assertEqual(s["nombre"], "Leads portal")
        self.assertEqual(s["hora_envio"], 7)
        self.assertEqual(s["pasos"][0]["dias"], 60)
        self.assertEqual(s["pasos"][0]["plantilla"], "segprimercontacto")

    def test_secuencia_sin_toques_o_sin_plantilla_se_rechaza(self):
        with self.assertRaises(HTTPException):
            limpiar_secuencia(SecuenciaReq(nombre="x", numero_id="n1", pasos=[]))
        with self.assertRaises(HTTPException):
            limpiar_secuencia(SecuenciaReq(nombre="x", numero_id="n1", pasos=[PasoReq(plantilla="  ")]))

    def test_variables_nunca_vacias_y_con_saludo(self):
        self.assertEqual(render_variables(["{nombre}", "{agente}", ""], {"nombre": "juan pérez", "agente": "Salvador"}),
                         ["Juan", "Salvador", "-"])
        self.assertEqual(primer_nombre("5214431234567"), "qué tal")
        self.assertEqual(primer_nombre(None), "qué tal")

    def test_horario_lunes_a_sabado(self):
        domingo = datetime(2026, 11, 29, 17, 0, tzinfo=UTC)  # 11:00 en CDMX
        lunes = datetime(2026, 11, 30, 17, 0, tzinfo=UTC)
        noche = datetime(2026, 12, 1, 4, 0, tzinfo=UTC)      # 22:00 en CDMX
        self.assertFalse(en_horario(domingo, "America/Mexico_City"))
        self.assertTrue(en_horario(lunes, "America/Mexico_City"))
        self.assertFalse(en_horario(noche, "America/Mexico_City"))

    def test_programar_a_la_hora_local(self):
        desde = datetime(2026, 11, 27, 22, 0, tzinfo=UTC)
        siguiente = programar(desde, 2, 10, "America/Mexico_City")
        self.assertEqual(siguiente, datetime(2026, 11, 29, 16, 0, tzinfo=UTC))
        self.assertEqual(programar(desde, 0, 10, "America/Mexico_City"), desde)

    def test_clasificacion_de_errores_de_meta(self):
        self.assertEqual(clasificar_error({"code": 131050}), "baja")
        self.assertEqual(clasificar_error({"code": "132001"}), "plantilla")
        self.assertEqual(clasificar_error({"code": 190}), "token")
        self.assertEqual(clasificar_error({"code": 131026}), "invalido")
        self.assertEqual(clasificar_error({"message": "timeout"}), "reintentar")

    def test_puntaje_transparente(self):
        ahora = datetime(2026, 11, 27, 18, 0, tzinfo=UTC)
        conv = {"last_inbound_at": (ahora - timedelta(hours=2)).isoformat(),
                "last_message_at": (ahora - timedelta(hours=2)).isoformat()}
        entrantes = [{"body": "Hola"}, {"body": "¿Puedo ir a verla el sábado?"}, {"body": "Tengo crédito Infonavit"}]
        puntos, razones = puntuar(conv, entrantes, True, ahora)
        self.assertEqual(razones[0], "Está esperando tu respuesta")
        self.assertIn("Pidió visita", razones)
        self.assertIn("Habló de crédito", razones)
        self.assertIn("Contestó tu seguimiento", razones)
        self.assertLessEqual(puntos, 100)
        frio, _ = puntuar({"last_inbound_at": (ahora - timedelta(days=10)).isoformat()}, [], False, ahora)
        self.assertEqual(frio, 0)

    def test_precio_y_titulo_de_inmueble(self):
        self.assertEqual(precio_de({"precio": None, "operaciones": [{"precio": "3500000"}]}), 3500000.0)
        self.assertIsNone(precio_de({"precio": 0}))
        self.assertEqual(precio_texto(3500000, "MXN"), "$3,500,000 MXN")
        self.assertEqual(titulo_de({"titulo": "Casa", "colonia": "Tres Marías", "ciudad": "Morelia"}),
                         "Casa en Tres Marías, Morelia")


class AccesoPiloto(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(api.router)
        self.client = TestClient(app)

    def _como(self, user, lista):
        return patch.multiple(datos, settings=SimpleNamespace(cecil_ui_user_ids=lista),
                              require_user_id=AsyncMock(return_value=user))

    def test_acceso_solo_para_la_lista_exacta(self):
        with self._como("owner", " owner , otro "), patch.object(api, "require_user_id", AsyncMock(return_value="owner")):
            self.assertTrue(self.client.get("/seguimiento/acceso").json()["piloto"])
        with self._como("owner-extra", "owner"), patch.object(api, "require_user_id", AsyncMock(return_value="owner-extra")):
            self.assertFalse(self.client.get("/seguimiento/acceso").json()["piloto"])

    def test_cuenta_fuera_del_piloto_recibe_403(self):
        with self._como("intruso", "owner"):
            self.assertEqual(self.client.get("/seguimiento/resumen").status_code, 403)
            self.assertEqual(self.client.post("/seguimiento/correr").status_code, 403)

    def test_lista_vacia_cierra_todo(self):
        with self._como("owner", ""):
            self.assertEqual(self.client.get("/seguimiento/secuencias").status_code, 403)

    def test_sin_sesion_401(self):
        self.assertEqual(self.client.get("/seguimiento/acceso").status_code, 401)


class MotorDeToques(unittest.TestCase):
    def _correr(self, inscripcion, contacto, error=None):
        ahora = datetime(2026, 11, 30, 17, 0, tzinfo=UTC)
        secuencia = {"id": "s1", "nombre": "Portal", "activa": True, "numero_id": "n1", "hora_envio": 10,
                     "pasos": [{"dias": 0, "plantilla": "seg_a", "idioma": "es_MX", "variables": ["{nombre}"]},
                               {"dias": 2, "plantilla": "seg_b", "idioma": "es_MX", "variables": []}]}

        async def leer(tabla, params):
            return [inscripcion] if tabla == "seg_inscripciones" else [secuencia]

        cambios = []

        async def actualizar(tabla, params, body):
            cambios.append((params, body))
            return [{"id": "i1"}]

        enviar = AsyncMock(return_value=({"id": "c1"}, error))
        with patch.multiple(motor, leer=leer, actualizar=actualizar, contacto_de=AsyncMock(return_value=contacto),
                            proximo_permitido=AsyncMock(return_value=None), numero_de=AsyncMock(return_value={"id": "n1"}),
                            perfil_agente=AsyncMock(return_value={"nombre": "Salvador", "zona": "Morelia"}),
                            enviar_plantilla=enviar):
            enviados = asyncio.run(motor.correr_toques("u1", "America/Mexico_City", ahora, 10))
        return enviados, cambios, enviar

    def test_toque_avanza_y_programa_el_siguiente(self):
        ins = {"id": "i1", "secuencia_id": "s1", "contacto_id": "k1", "paso": 0, "estado": "activa"}
        enviados, cambios, enviar = self._correr(ins, {"id": "k1", "nombre": "juan", "wa_id": "52443"})
        self.assertEqual(enviados, 1)
        self.assertEqual(enviar.call_args.args[5], ["Juan"])
        final = cambios[-1][1]
        self.assertEqual(final["paso"], 1)
        self.assertEqual(final["proximo_en"], datetime(2026, 12, 2, 16, 0, tzinfo=UTC).isoformat())

    def test_ultimo_toque_termina_la_secuencia(self):
        ins = {"id": "i1", "secuencia_id": "s1", "contacto_id": "k1", "paso": 1, "estado": "activa"}
        _, cambios, _ = self._correr(ins, {"id": "k1", "nombre": "Ana", "wa_id": "52443"})
        self.assertEqual(cambios[-1][1]["estado"], "terminada")

    def test_baja_no_se_le_escribe(self):
        ins = {"id": "i1", "secuencia_id": "s1", "contacto_id": "k1", "paso": 0, "estado": "activa"}
        enviados, cambios, enviar = self._correr(ins, {"id": "k1", "nombre": "Ana", "opt_out": True})
        self.assertEqual(enviados, 0)
        enviar.assert_not_called()
        self.assertEqual(cambios[-1][1]["estado"], "baja")

    def test_plantilla_rechazada_cierra_con_motivo(self):
        ins = {"id": "i1", "secuencia_id": "s1", "contacto_id": "k1", "paso": 0, "estado": "activa"}
        _, cambios, _ = self._correr(ins, {"id": "k1", "nombre": "Ana", "wa_id": "1"}, error={"code": 132001})
        self.assertEqual(cambios[-1][1]["estado"], "error")
        self.assertIn("seg_a", cambios[-1][1]["motivo"])


if __name__ == "__main__":
    unittest.main()
