"""El editor de imágenes debe tratar igual a todas las fotos de una tanda.

Regresiones que cubren estas pruebas:
- Con IA, si la primera llamada a Gemini no regresaba imagen, se reintentaba
  con un payload de SOLO TEXTO y Gemini inventaba otra casa/cuarto.
- Gemini podía regresar otra proporción (cuadrada) y se entregaba tal cual.
- Sin IA, el balance de blancos "gray world" pintaba de magenta o azul las
  zonas grises de fotos con mucho verde (jardín) o madera.
"""
import asyncio
import base64
import io
import types
import unittest

try:
    import numpy as np
    from PIL import Image
    import routers.image_cleaner as ic
except Exception as exc:  # pragma: no cover - depende del entorno
    raise unittest.SkipTest(f"dependencias de imagen no disponibles: {exc}")


def _jpeg(arr) -> bytes:
    b = io.BytesIO()
    Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8)).save(b, "JPEG", quality=95)
    return b.getvalue()


def _png_b64(size) -> str:
    b = io.BytesIO()
    Image.new("RGB", size, (10, 200, 10)).save(b, "PNG")
    return base64.b64encode(b.getvalue()).decode()


class _Resp:
    def __init__(self, code, data):
        self.status_code = code
        self._data = data
        self.text = str(data)

    def json(self):
        return self._data


class GeminiSiempreEditaLaFotoTests(unittest.TestCase):
    def setUp(self):
        self._orig_client = ic.httpx.AsyncClient
        self._orig_settings = ic.settings
        ic.settings = types.SimpleNamespace(gemini_api_key="k", gemini_image_model="")

    def tearDown(self):
        ic.httpx.AsyncClient = self._orig_client
        ic.settings = self._orig_settings

    def _correr(self, respuestas, size=(4000, 3000)):
        llamadas = []

        class Cliente:
            def __init__(self, **kw):
                pass

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

            async def post(self, url, json, headers):
                llamadas.append(json)
                return respuestas.pop(0)

        ic.httpx.AsyncClient = Cliente
        out = asyncio.run(ic._process_with_gemini(
            _jpeg(np.full((size[1], size[0], 3), 120.0)), "image/jpeg", "vaciar el cuarto"))
        return out, llamadas

    def test_ningun_reintento_va_sin_la_foto(self):
        respuestas = [
            _Resp(200, {"candidates": [{"content": {"parts": [{"text": "no puedo"}]}}]}),
            _Resp(200, {"candidates": [{"finishReason": "IMAGE_SAFETY"}]}),
            _Resp(200, {"candidates": [{"content": {"parts": [
                {"inlineData": {"data": _png_b64((1024, 1024))}}]}}]}),
        ]
        _, llamadas = self._correr(respuestas)
        self.assertEqual(len(llamadas), 3)
        for payload in llamadas:
            partes = payload["contents"][0]["parts"]
            self.assertTrue(any("inline_data" in p for p in partes),
                            "se mandó a Gemini un payload sin la foto")

    def test_resultado_conserva_proporcion_y_tamano(self):
        respuestas = [_Resp(200, {"candidates": [{"content": {"parts": [
            {"inlineData": {"data": _png_b64((1024, 1024))}}]}}]})]
        out, llamadas = self._correr(respuestas, size=(4000, 3000))
        self.assertEqual(Image.open(io.BytesIO(out)).size, (1024, 768))
        self.assertEqual(
            llamadas[0]["generationConfig"]["imageConfig"]["aspectRatio"], "4:3")


@unittest.skipUnless(ic.CV2_AVAILABLE, "opencv no disponible")
class BalanceDeBlancosTests(unittest.TestCase):
    def _gris_del_piso(self, color_dominante):
        arr = np.full((600, 800, 3), color_dominante, np.float32)
        arr[400:] = [120, 120, 120]
        out, _ = ic._process_image_sync(_jpeg(arr), "image/jpeg")
        o = np.array(Image.open(io.BytesIO(out))).astype(float)
        return o[450:].reshape(-1, 3).mean(0)

    def test_piso_gris_sigue_gris_en_foto_de_jardin_o_madera(self):
        for nombre, color in (("jardin", [60, 140, 50]), ("madera", [170, 110, 60]),
                              ("cielo", [90, 150, 220])):
            r, g, b = self._gris_del_piso(color)
            self.assertLess(max(r, g, b) - min(r, g, b), 10,
                            f"{nombre}: el piso gris salió con dominante ({r:.0f},{g:.0f},{b:.0f})")


if __name__ == "__main__":
    unittest.main()
