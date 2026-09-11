"""Permanent guards for Google Places AVM colonia lookup."""
import asyncio
from pathlib import Path
from unittest import mock
import unittest

ROOT = Path(__file__).resolve().parents[1]


class MainAvmPlacesExtractionTests(unittest.TestCase):
    def test_places_colonia_contract_is_preserved(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        router = (ROOT / "routers" / "avm_places.py").read_text(encoding="utf-8")

        self.assertIn('@router.get("/api/colonias")', router)
        self.assertIn('if len(texto) < 3:', router)
        self.assertIn('return {"colonias": [], "error": "GOOGLE_PLACES_KEY no configurada"}', router)
        self.assertIn('httpx.AsyncClient(timeout=15)', router)
        self.assertIn('_LOCATIONBIAS = "circle:50000@19.7059504,-101.1949825"', router)
        # Los parámetros que se arman para Autocomplete ya no incluyen
        # "types": restringirlo (a "geocode" o a "(regions)") fue lo que
        # hacía desaparecer desarrollos como Altozano, indexados por Google
        # como establecimiento/punto de interés y no como "region". La
        # prueba de comportamiento de abajo confirma que ese tipo de
        # resultado sí pasa el filtro ahora.
        self.assertNotIn('params = {\n        "input": texto,\n        "types"', router)
        self.assertIn('"strictbounds"] = "true"', router)
        self.assertIn('httpx.AsyncClient(timeout=10)', router)
        self.assertIn('resultado = {"colonias": colonias[:6]}', router)
        self.assertIn('cache_set(cache_key, resultado, ttl=86400)', router)
        self.assertIn('from routers.avm_places import router as avm_places_router', main)
        self.assertNotIn('@app.get("/api/colonias")', main)
        # El inventario propio de EasyBroker se consulta junto con Google —
        # ver test_combinar_inventario_* de abajo para el comportamiento.
        self.assertIn(
            'from core.easybroker import EB_API_KEY, construir_mapa_colonias, normalize as eb_normalize',
            router,
        )
        self.assertIn('inventario, locales, nacionales = await asyncio.gather(', router)
        compile(router, "routers/avm_places.py", "exec")
        compile(main, "main.py", "exec")

    def _cargar_router(self):
        import importlib
        return importlib.import_module("routers.avm_places")

    def test_combinar_candidatos_prefiere_lo_local_y_no_duplica(self):
        m = self._cargar_router()
        local = {"place_id": "A", "types": ["sublocality"], "description": "A local"}
        nacional_dup = {"place_id": "A", "types": ["sublocality"], "description": "A local"}
        nacional_otro = {"place_id": "B", "types": ["neighborhood"], "description": "B nacional"}
        out = m._combinar_candidatos([local], [nacional_dup, nacional_otro])
        self.assertEqual([p["place_id"] for p in out], ["A", "B"])

    def test_combinar_candidatos_acepta_establecimientos_tipo_altozano(self):
        # Altozano es justo este caso: Google lo indexa como point_of_interest/
        # establishment (una plaza/desarrollo), no como sublocality.
        m = self._cargar_router()
        altozano = {"place_id": "ALT", "types": ["point_of_interest", "establishment"], "description": "Altozano, Morelia"}
        out = m._combinar_candidatos([altozano], [])
        self.assertEqual([p["place_id"] for p in out], ["ALT"])

    def test_combinar_candidatos_descarta_tipos_demasiado_amplios(self):
        m = self._cargar_router()
        ciudad = {"place_id": "C1", "types": ["locality", "political"], "description": "Morelia"}
        estado = {"place_id": "C2", "types": ["administrative_area_level_1"], "description": "Michoacán"}
        cp = {"place_id": "C3", "types": ["postal_code"], "description": "58000"}
        calle = {"place_id": "C4", "types": ["route"], "description": "Av. Madero"}
        domicilio = {"place_id": "C5", "types": ["street_address"], "description": "Av. Madero 123"}
        colonia = {"place_id": "C6", "types": ["sublocality"], "description": "Chapultepec, Morelia"}
        out = m._combinar_candidatos([ciudad, estado, cp, calle, domicilio, colonia], [])
        self.assertEqual([p["place_id"] for p in out], ["C6"])

    def test_combinar_candidatos_respeta_el_tope_de_candidatos(self):
        m = self._cargar_router()
        locales = [{"place_id": str(i), "types": ["sublocality"]} for i in range(5)]
        nacionales = [{"place_id": str(i), "types": ["sublocality"]} for i in range(5, 20)]
        out = m._combinar_candidatos(locales, nacionales, max_candidatos=8)
        self.assertEqual(len(out), 8)
        self.assertEqual([p["place_id"] for p in out[:5]], ["0", "1", "2", "3", "4"])

    def test_coincide_inventario_escritura_parcial_y_desambiguacion_por_ciudad(self):
        m = self._cargar_router()
        # Mientras se teclea: el texto es más corto que la colonia.
        self.assertTrue(m._coincide_inventario("monte", "jesus del monte"))
        # El usuario agrega la ciudad a propósito para desambiguar de una
        # tocaya en otro estado: la colonia es más corta que lo escrito.
        self.assertTrue(m._coincide_inventario("jesus del monte morelia", "jesus del monte"))
        self.assertFalse(m._coincide_inventario("chapultepec", "jesus del monte"))

    def _limpiar_cache_inventario(self, m):
        from core.cache import _CACHE
        _CACHE.pop(f"colonias_inventario_{m.eb_normalize(m._CIUDAD_NEGOCIO)}", None)

    def test_colonias_de_inventario_sin_api_key_no_intenta_nada(self):
        m = self._cargar_router()
        self._limpiar_cache_inventario(m)
        fake_mapa = mock.AsyncMock(side_effect=AssertionError("no debía llamarse sin EB_API_KEY"))
        with mock.patch.object(m, "EB_API_KEY", ""), mock.patch.object(m, "construir_mapa_colonias", fake_mapa):
            out = asyncio.run(m._colonias_de_inventario("altozano"))
        self.assertEqual(out, [])

    def test_colonias_de_inventario_encuentra_altozano_y_colonia_mas_ciudad(self):
        m = self._cargar_router()
        self._limpiar_cache_inventario(m)
        mapa = {"Altozano": 12, "Jesus del Monte": 5, "Chapultepec": 3}

        async def fake_mapa(ciudad):
            self.assertEqual(ciudad, "Morelia")
            return mapa

        with mock.patch.object(m, "EB_API_KEY", "test-key"), mock.patch.object(m, "construir_mapa_colonias", fake_mapa):
            self.assertEqual(asyncio.run(m._colonias_de_inventario("altozano")), ["Altozano"])
            # El mapa ya quedó en caché — esta segunda búsqueda no necesita
            # volver a "llamar a EasyBroker" (fake_mapa reafirma la ciudad
            # solo si se invoca; el resultado debe seguir siendo correcto).
            self.assertEqual(
                asyncio.run(m._colonias_de_inventario("jesus del monte morelia")),
                ["Jesus del Monte"],
            )

    def test_colonias_de_inventario_ordena_por_frecuencia(self):
        m = self._cargar_router()
        self._limpiar_cache_inventario(m)

        async def fake_mapa(ciudad):
            return {"Norte": 2, "Norte Alto": 9}

        with mock.patch.object(m, "EB_API_KEY", "test-key"), mock.patch.object(m, "construir_mapa_colonias", fake_mapa):
            out = asyncio.run(m._colonias_de_inventario("norte"))
        self.assertEqual(out, ["Norte Alto", "Norte"])


if __name__ == "__main__":
    unittest.main()
