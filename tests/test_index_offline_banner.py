"""Bug real reportado en producción: el banner "Sin conexión · datos de"
aparecía encima de una pantalla con datos frescos y recién cargados (texto
vacío después de "datos de", incluido) porque se apoyaba únicamente en
`navigator.onLine` — una bandera que solo dice si el sistema operativo tiene
una interfaz de red activa, no si Internet responde de verdad, y que en
iPadOS/Safari puede leer `false` por unos segundos sin que ninguna petición
real haya fallado.

El arreglo: el banner ya no se muestra por sí solo al cargar la página ni
por el evento `offline`. Solo lo enciende `window.brokrReportarConexion(false)`
—llamado desde fxCount/fxRest cuando una petición real de verdad no se pudo
completar— y solo si además `navigator.onLine` confirma `false`; cualquier
petición que sí obtuvo respuesta del servidor (exitosa o no) lo apaga.

Estas pruebas ejecutan de verdad (con Node, DOM mínimo simulado) el código
de index.html en vez de solo buscar texto en el archivo, para que una
regresión futura se detecte aquí y no en producción otra vez.
"""
import re
import shutil
import subprocess
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "index.html"
NODE = shutil.which("node")


def _inline_scripts(html: str) -> list[str]:
    return re.findall(r"<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)</script>", html)


def _extraer_bloque(source: str, marcador: str, apertura_txt: str) -> str:
    """Extrae un bloque balanceado en llaves que empieza en `apertura_txt`
    después de la primera aparición de `marcador`."""
    ancla = source.index(marcador)
    inicio = source.index(apertura_txt, ancla)
    llave = source.index("{", inicio)
    profundidad = 0
    for j in range(llave, len(source)):
        if source[j] == "{":
            profundidad += 1
        elif source[j] == "}":
            profundidad -= 1
            if profundidad == 0:
                # Incluye el ")();" final si el bloque es una IIFE.
                cierre = j + 1
                resto = source[cierre:cierre + 4]
                if resto.startswith(")();"):
                    cierre += 4
                return source[inicio:cierre]
    raise AssertionError(f"no se encontró el cierre del bloque tras {marcador!r}")


def _extraer_funcion(source: str, nombre: str) -> str:
    inicio = source.index(f"function {nombre}(")
    if source[max(0, inicio - 6):inicio] == "async ":
        inicio -= 6
    apertura = source.index("{", inicio)
    profundidad = 0
    for j in range(apertura, len(source)):
        if source[j] == "{":
            profundidad += 1
        elif source[j] == "}":
            profundidad -= 1
            if profundidad == 0:
                return source[inicio:j + 1]
    raise AssertionError(f"no se encontró el cierre de function {nombre}()")


class OfflineBannerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not NODE:
            raise unittest.SkipTest("node no está disponible en este entorno")
        html = HTML.read_text(encoding="utf-8")
        scripts = _inline_scripts(html)
        banner_script = next(s for s in scripts if 'Banner "sin conexión"' in s)
        cls.banner_iife = _extraer_bloque(
            banner_script, 'Banner "sin conexión"', "(function ()")

        fx_script = next(s for s in scripts if "async function fxCount(" in s)
        cls.fx_funcs = "\n".join(
            _extraer_funcion(fx_script, nombre) for nombre in ("fxCount", "fxRest")
        )

    def _run(self, setup_js: str, body_js: str) -> str:
        script = setup_js + "\n" + self.banner_iife + "\n" + body_js
        proc = subprocess.run(
            [NODE, "-e", script], capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def _dom_stub(self, *, online: bool, ultima_carga: str = "null") -> str:
        return f"""
        const _banner = {{ hidden: true }};
        const _hora = {{ textContent: '' }};
        const document = {{
          getElementById(id) {{
            if (id === 'dash-offline') return _banner;
            if (id === 'dash-offline-hora') return _hora;
            return null;
          }},
        }};
        const window = {{ addEventListener() {{}} }};
        const navigator = {{ onLine: {str(online).lower()} }};
        const localStorage = {{ getItem: () => {ultima_carga} }};
        """

    def test_reporte_de_falla_estando_en_linea_NO_muestra_el_banner(self):
        # Este es exactamente el bug reportado: navigator.onLine puede leer
        # `false` sin razón real, pero si en ese instante SÍ estamos en
        # línea (onLine: true), una falla nunca debe mostrar el banner.
        out = self._run(
            self._dom_stub(online=True),
            "window.brokrReportarConexion(false); console.log(_banner.hidden);",
        )
        self.assertEqual(out, "true")

    def test_ninguna_llamada_no_muestra_nada_al_cargar(self):
        # Antes, el script se auto-invocaba y decidía por su cuenta con
        # navigator.onLine al cargar la página — eso es lo que producía el
        # falso positivo. Ahora, sin ninguna petición real de por medio, el
        # banner debe quedarse tal cual estaba en el HTML (oculto).
        out = self._run(self._dom_stub(online=False), "console.log(_banner.hidden);")
        self.assertEqual(out, "true")

    def test_falla_real_estando_offline_SI_muestra_el_banner(self):
        out = self._run(
            self._dom_stub(online=False),
            "window.brokrReportarConexion(false); console.log(_banner.hidden);",
        )
        self.assertEqual(out, "false")

    def test_texto_de_hora_nunca_queda_vacio_sin_carga_previa(self):
        # El otro síntoma del bug: "datos de" con el span vacío.
        out = self._run(
            self._dom_stub(online=False, ultima_carga="null"),
            "window.brokrReportarConexion(false); console.log(JSON.stringify(_hora.textContent));",
        )
        self.assertEqual(out, '"esta sesión"')
        self.assertNotEqual(out, '""')

    def test_texto_de_hora_usa_la_ultima_carga_guardada(self):
        out = self._run(
            self._dom_stub(online=False, ultima_carga="'2026-09-12T03:04:00.000Z'"),
            "window.brokrReportarConexion(false); console.log(JSON.stringify(_hora.textContent));",
        )
        self.assertNotEqual(out, '""')
        self.assertNotEqual(out, '"esta sesión"')

    def test_una_peticion_exitosa_oculta_el_banner(self):
        out = self._run(
            self._dom_stub(online=False),
            "window.brokrReportarConexion(false);"
            "window.brokrReportarConexion(true);"
            "console.log(_banner.hidden);",
        )
        self.assertEqual(out, "true")

    def test_fxcount_avisa_conexion_ok_en_una_respuesta_http_de_error(self):
        # Un 401/500 es una respuesta real del servidor: SÍ hay red, solo
        # falló la petición por otra razón — nunca debe encender el banner.
        setup = """
        const SB_URL = 'https://x.test';
        const SB_KEY = 'anon';
        const localStorage = { getItem: () => null };
        const sessionStorage = { getItem: () => null };
        const avisos = [];
        const window = { brokrSb: undefined, brokrReportarConexion: (ok) => avisos.push(ok) };
        global.fetch = async () => ({ ok: false, status: 500, headers: { get: () => null } });
        """
        script = setup + "\n" + self.fx_funcs + "\n" + \
            "fxCount('tareas?select=id').then(() => console.log(JSON.stringify(avisos)));"
        proc = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "[true]")

    def test_fxcount_avisa_falla_real_cuando_fetch_truena(self):
        setup = """
        const SB_URL = 'https://x.test';
        const SB_KEY = 'anon';
        const localStorage = { getItem: () => null };
        const sessionStorage = { getItem: () => null };
        const avisos = [];
        const window = { brokrSb: undefined, brokrReportarConexion: (ok) => avisos.push(ok) };
        global.fetch = async () => { throw new TypeError('Failed to fetch'); };
        """
        script = setup + "\n" + self.fx_funcs + "\n" + \
            "fxCount('tareas?select=id').then(() => console.log(JSON.stringify(avisos)));"
        proc = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "[false]")

    def test_fxrest_avisa_conexion_ok_al_recibir_json(self):
        setup = """
        const SB_URL = 'https://x.test';
        const SB_KEY = 'anon';
        const localStorage = { getItem: () => 'tok-123' };
        const sessionStorage = { getItem: () => null };
        const avisos = [];
        const window = { brokrSb: undefined, brokrReportarConexion: (ok) => avisos.push(ok) };
        global.fetch = async () => ({ ok: true, status: 200, json: async () => ([]) });
        """
        script = setup + "\n" + self.fx_funcs + "\n" + \
            "fxRest('tareas?select=id').then(() => console.log(JSON.stringify(avisos)));"
        proc = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "[true]")

    def test_files_compile(self):
        import tempfile
        import os
        html = HTML.read_text(encoding="utf-8")
        for i, s in enumerate(_inline_scripts(html)):
            with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
                f.write(s)
                ruta = f.name
            try:
                proc = subprocess.run([NODE, "--check", ruta], capture_output=True, text=True, timeout=10)
                self.assertEqual(proc.returncode, 0, f"script {i}: {proc.stderr}")
            finally:
                os.unlink(ruta)


if __name__ == "__main__":
    unittest.main()
