"""Regression tests for the Gemini-assisted tour planning in routers/video.py.

Ground rules asserted here, matching the module's own documented policy:
- Without a usable plan (no API key, bad response, invalid order), the video
  must render exactly as it always did: same photo order, same alternating
  Ken Burns pattern.
- A valid plan only ever changes photo order and camera direction/focus; it
  never touches a pixel — `_planear_recorrido` returns plain data, not media.
- Any failure in the planning path is swallowed; it must never propagate and
  block a video render.
"""
from __future__ import annotations

import json
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import routers.video as video


class Clamp01Tests(unittest.TestCase):
    def test_clamps_out_of_range_values(self):
        self.assertEqual(video._clamp01(-0.5), 0.0)
        self.assertEqual(video._clamp01(1.7), 1.0)
        self.assertEqual(video._clamp01(0.42), 0.42)

    def test_invalid_input_defaults_to_center(self):
        self.assertEqual(video._clamp01(None), 0.5)
        self.assertEqual(video._clamp01("no-numero"), 0.5)


class FiltroKenBurnsBackwardCompatTests(unittest.TestCase):
    """Sin movimiento explícito, el filtro debe seguir siendo el de siempre."""

    def _formula(self, idx: int) -> str:
        filtro = video._filtro_ken_burns(idx, 1920, 1080)
        return filtro.split("zoompan=", 1)[1].split(":d=", 1)[0]

    def test_modo_0_es_zoom_centrado(self):
        self.assertIn("x='iw*0.500-(iw/zoom/2)'", self._formula(0))
        self.assertIn("y='ih*0.500-(ih/zoom/2)'", self._formula(0))

    def test_modo_1_es_pan_izquierda_a_derecha(self):
        formula = self._formula(1)
        self.assertIn(f"z='{video.ZOOM_MAX}'", formula)
        self.assertIn("x='(iw-iw/zoom)*(on/", formula)
        self.assertIn("y='ih*0.500-(ih/zoom/2)'", formula)

    def test_modo_2_es_zoom_con_foco_mas_bajo(self):
        self.assertIn("y='ih*0.600-(ih/zoom/2)'", self._formula(2))

    def test_modo_3_es_pan_derecha_a_izquierda(self):
        formula = self._formula(3)
        self.assertIn("x='(iw-iw/zoom)*(1-on/", formula)

    def test_ciclo_de_cuatro_se_repite(self):
        self.assertEqual(self._formula(0), self._formula(4))


class FiltroKenBurnsConPlanTests(unittest.TestCase):
    def test_zoom_in_usa_el_foco_dado(self):
        formula = video._filtro_ken_burns(
            0, 1920, 1080, {"tipo": "zoom_in", "foco_x": 0.8, "foco_y": 0.3},
        )
        self.assertIn("x='iw*0.800-(iw/zoom/2)'", formula)
        self.assertIn("y='ih*0.300-(ih/zoom/2)'", formula)

    def test_movimiento_invalido_cae_al_patron_de_siempre(self):
        con_basura = video._filtro_ken_burns(0, 1920, 1080, {"tipo": "vuela"})
        sin_plan = video._filtro_ken_burns(0, 1920, 1080, None)
        self.assertEqual(con_basura, sin_plan)


class ConstruirComandoTests(unittest.TestCase):
    def test_movimientos_se_alinean_por_indice(self):
        movs = [
            {"tipo": "zoom_in", "foco_x": 0.9, "foco_y": 0.1},
            None,
        ]
        cmd = video._construir_comando(["a.jpg", "b.jpg"], "/tmp/out.mp4", "16:9", movs)
        filtro = cmd[cmd.index("-filter_complex") + 1]
        segmento_foto_0 = filtro.split(";")[0]
        self.assertTrue(segmento_foto_0.startswith("[0:v]"))
        self.assertIn("x='iw*0.900-(iw/zoom/2)'", segmento_foto_0)


class PlanearRecorridoTests(unittest.IsolatedAsyncioTestCase):
    def _mock_response(self, status_code: int, payload: dict | None = None):
        resp = MagicMock()
        resp.status_code = status_code
        if payload is not None:
            resp.json.return_value = payload
        return resp

    async def test_sin_api_key_regresa_none_sin_tocar_la_red(self):
        with patch.object(video, "GEMINI_API_KEY", ""):
            with patch("routers.video.httpx.AsyncClient") as cliente:
                resultado = await video._planear_recorrido(["a.jpg", "b.jpg"], "user-1")
        self.assertIsNone(resultado)
        cliente.assert_not_called()

    async def test_una_sola_foto_regresa_none(self):
        with patch.object(video, "GEMINI_API_KEY", "clave"):
            resultado = await video._planear_recorrido(["a.jpg"], "user-1")
        self.assertIsNone(resultado)

    async def test_orden_invalido_se_descarta(self):
        payload = {
            "candidates": [{"content": {"parts": [
                {"text": json.dumps({"orden": [0, 0, 2], "fotos": []})},
            ]}}],
        }
        cliente = AsyncMock()
        cliente.post.return_value = self._mock_response(200, payload)
        contexto = AsyncMock()
        contexto.__aenter__.return_value = cliente
        contexto.__aexit__.return_value = False

        with (
            patch.object(video, "GEMINI_API_KEY", "clave"),
            patch("routers.video.httpx.AsyncClient", return_value=contexto),
            patch.object(video, "_miniatura_b64", return_value="ZmFrZQ=="),
        ):
            resultado = await video._planear_recorrido(["a.jpg", "b.jpg", "c.jpg"], "user-1")
        self.assertIsNone(resultado)

    async def test_respuesta_valida_reordena_y_trackea_uso(self):
        payload = {
            "candidates": [{"content": {"parts": [{"text": json.dumps({
                "orden": [2, 0, 1],
                "fotos": [
                    {"indice": 0, "movimiento": "zoom_in", "foco_x": 0.6, "foco_y": 0.4},
                    {"indice": 1, "movimiento": "pan_der_a_izq", "foco_x": 0.0, "foco_y": 0.5},
                    {"indice": 2, "movimiento": "algo-que-no-existe", "foco_x": 2.0, "foco_y": -1.0},
                ],
            })}]}}],
            "usageMetadata": {"promptTokenCount": 120, "candidatesTokenCount": 30},
        }
        cliente = AsyncMock()
        cliente.post.return_value = self._mock_response(200, payload)
        contexto = AsyncMock()
        contexto.__aenter__.return_value = cliente
        contexto.__aexit__.return_value = False

        with (
            patch.object(video, "GEMINI_API_KEY", "clave"),
            patch("routers.video.httpx.AsyncClient", return_value=contexto),
            patch.object(video, "_miniatura_b64", return_value="ZmFrZQ=="),
            patch("routers.video.track_usage", new=AsyncMock()) as track,
        ):
            resultado = await video._planear_recorrido(["f0.jpg", "f1.jpg", "f2.jpg"], "user-1")

        self.assertEqual(resultado["orden"], [2, 0, 1])
        # movimientos[0] es la foto original 2: movimiento inválido -> cae a
        # zoom_in, pero foco_x/foco_y sí se respetan una vez recortados a [0,1].
        self.assertEqual(resultado["movimientos"][0], {"tipo": "zoom_in", "foco_x": 1.0, "foco_y": 0.0})
        self.assertEqual(resultado["movimientos"][1], {"tipo": "zoom_in", "foco_x": 0.6, "foco_y": 0.4})
        self.assertEqual(resultado["movimientos"][2], {"tipo": "pan_der_a_izq", "foco_x": 0.0, "foco_y": 0.5})
        track.assert_awaited_once()
        _, kwargs = track.await_args
        self.assertEqual(kwargs["user_id"], "user-1")
        self.assertEqual(kwargs["modulo"], "video")
        self.assertEqual(kwargs["proveedor"], "gemini")
        self.assertEqual(kwargs["tokens_in"], 120)
        self.assertEqual(kwargs["tokens_out"], 30)

    async def test_cuota_agotada_regresa_none_sin_lanzar(self):
        cliente = AsyncMock()
        cliente.post.return_value = self._mock_response(429)
        contexto = AsyncMock()
        contexto.__aenter__.return_value = cliente
        contexto.__aexit__.return_value = False

        with (
            patch.object(video, "GEMINI_API_KEY", "clave"),
            patch("routers.video.httpx.AsyncClient", return_value=contexto),
            patch.object(video, "_miniatura_b64", return_value="ZmFrZQ=="),
        ):
            resultado = await video._planear_recorrido(["a.jpg", "b.jpg"], "user-1")
        self.assertIsNone(resultado)

    async def test_json_invalido_no_lanza(self):
        payload = {"candidates": [{"content": {"parts": [{"text": "esto no es json"}]}}]}
        cliente = AsyncMock()
        cliente.post.return_value = self._mock_response(200, payload)
        contexto = AsyncMock()
        contexto.__aenter__.return_value = cliente
        contexto.__aexit__.return_value = False

        with (
            patch.object(video, "GEMINI_API_KEY", "clave"),
            patch("routers.video.httpx.AsyncClient", return_value=contexto),
            patch.object(video, "_miniatura_b64", return_value="ZmFrZQ=="),
        ):
            resultado = await video._planear_recorrido(["a.jpg", "b.jpg"], "user-1")
        self.assertIsNone(resultado)


class AplicarPlanRecorridoTests(unittest.IsolatedAsyncioTestCase):
    async def test_sin_plan_regresa_orden_original(self):
        with patch.object(video, "_planear_recorrido", new=AsyncMock(return_value=None)):
            locales, movimientos = await video._aplicar_plan_recorrido(
                ["a.jpg", "b.jpg"], "user-1",
            )
        self.assertEqual(locales, ["a.jpg", "b.jpg"])
        self.assertIsNone(movimientos)

    async def test_con_plan_reordena_las_rutas_locales(self):
        plan = {"orden": [1, 0], "movimientos": [{"tipo": "zoom_in", "foco_x": 0.5, "foco_y": 0.5}] * 2}
        with patch.object(video, "_planear_recorrido", new=AsyncMock(return_value=plan)):
            locales, movimientos = await video._aplicar_plan_recorrido(
                ["a.jpg", "b.jpg"], "user-1",
            )
        self.assertEqual(locales, ["b.jpg", "a.jpg"])
        self.assertEqual(movimientos, plan["movimientos"])

    async def test_falla_de_planeacion_nunca_se_propaga(self):
        with patch.object(video, "_planear_recorrido", new=AsyncMock(side_effect=RuntimeError("boom"))):
            locales, movimientos = await video._aplicar_plan_recorrido(
                ["a.jpg", "b.jpg"], "user-1",
            )
        self.assertEqual(locales, ["a.jpg", "b.jpg"])
        self.assertIsNone(movimientos)


if __name__ == "__main__":
    unittest.main()
