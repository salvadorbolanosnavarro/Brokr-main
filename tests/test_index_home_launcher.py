"""El home dejó de ser un dashboard (KPIs del día, tareas, leads,
pipeline, últimos inmuebles) y se volvió un launcher de módulos: barra
superior (avatar · frase · logotipo), 3 KPIs de negocio y todos los
módulos en tarjetas. Estas pruebas ejecutan de verdad (con Node, DOM y
`fetch` mínimos simulados) el script que arma esa barra superior y esos
3 KPIs cuando `brokr-shell-ready` dispara, en vez de solo buscar texto
en el archivo — así una regresión futura en la lógica se detecta aquí.
"""
import json
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


class HomeLauncherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not NODE:
            raise unittest.SkipTest("node no está disponible en este entorno")
        html = HTML.read_text(encoding="utf-8")
        scripts = _inline_scripts(html)
        cls.script = next(s for s in scripts if "brokr-shell-ready" in s)

    def _harness(self, *, fetch_impl: str, detail: dict) -> dict:
        stub = """
        const _stores = { local: {}, session: {} };
        const localStorage = {
          getItem: (k) => (k in _stores.local ? _stores.local[k] : null),
          setItem: (k, v) => { _stores.local[k] = String(v); },
        };
        const sessionStorage = {
          getItem: (k) => (k in _stores.session ? _stores.session[k] : null),
          setItem: (k, v) => { _stores.session[k] = String(v); },
        };

        function fakeEl(id) {
          let _tc = '';
          return { id, get textContent() { return _tc; }, set textContent(v) { _tc = String(v); },
            innerHTML: '', hidden: false,
            _listeners: {},
            addEventListener(ev, fn) { this._listeners[ev] = fn; },
            insertAdjacentHTML(pos, html) { this.innerHTML += html; },
            setAttribute() {}, classList: { add(){}, remove(){} } };
        }

        const _els = {};
        ['home-phrase', 'home-kpi-activos', 'home-kpi-pros', 'home-kpi-cierres',
         'home-avatar', 'home-more-menu'].forEach(id => { _els[id] = fakeEl(id); });

        const document = {
          getElementById: (id) => _els[id] || null,
        };

        const _listeners = {};
        const window = {
          addEventListener: (ev, fn) => { _listeners[ev] = fn; },
          brokrSb: undefined,
          brokrReportarConexion: () => {},
        };

        global.fetch = """ + fetch_impl + """;
        """
        run = stub + "\n" + self.script + "\n" + f"""
        (async () => {{
          const fn = _listeners['brokr-shell-ready'];
          if (!fn) {{ console.log(JSON.stringify({{ error: 'no listener registered' }})); return; }}
          await fn({{ detail: {json.dumps(detail)} }});
          console.log(JSON.stringify({{
            phrase: _els['home-phrase'].innerHTML,
            activos: _els['home-kpi-activos'].textContent,
            pros: _els['home-kpi-pros'].textContent,
            cierres: _els['home-kpi-cierres'].textContent,
            avatarText: _els['home-avatar'].textContent,
            avatarHtml: _els['home-avatar'].innerHTML,
            masHtml: _els['home-more-menu'].innerHTML,
            ultimaCarga: _stores.local['brokr_ultima_carga'] || null,
          }}));
          process.exit(0); // el script deja un setInterval vivo (rotación de frases)
        }})();
        """
        proc = subprocess.run([NODE, "-e", run], capture_output=True, text=True, timeout=10)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout.strip().splitlines()[-1])

    def _fetch_conteos(self, activos: int, pros: int, cierres: int) -> str:
        # HEAD con Prefer: count=exact — la cuenta viaja en Content-Range.
        return f"""async (url, opts) => {{
          let total = 0;
          if (url.includes('propiedades')) total = {activos};
          else if (url.includes('contactos')) total = {pros};
          else if (url.includes('contratos')) total = {cierres};
          return {{ ok: true, status: 200, headers: {{ get: () => '0-0/' + total }} }};
        }}"""

    def test_los_3_kpis_reflejan_las_cuentas_reales(self):
        out = self._harness(
            fetch_impl=self._fetch_conteos(7, 3, 1),
            detail={"profile": {"user": {"id": "u1"}, "profile": {"nombre": "Ana López"}, "isAdmin": False}},
        )
        self.assertEqual(out["activos"], "7")
        self.assertEqual(out["pros"], "3")
        self.assertEqual(out["cierres"], "1")

    def test_inmuebles_activos_filtra_por_estatus_y_no_archivadas(self):
        # No es solo "cuántas propiedades hay": tiene que excluir vendidas/
        # archivadas o el número no significa "inventario activo".
        self.assertIn("estatus=eq.activa", self.script)
        self.assertIn("archivada=not.is.true", self.script)

    def test_avatar_usa_iniciales_cuando_no_hay_foto(self):
        out = self._harness(
            fetch_impl=self._fetch_conteos(0, 0, 0),
            detail={"profile": {"user": {"id": "u1"}, "profile": {"nombre": "Ana López"}, "isAdmin": False}},
        )
        self.assertEqual(out["avatarText"], "AL")

    def test_admin_no_ve_la_tarjeta_de_admin(self):
        out = self._harness(
            fetch_impl=self._fetch_conteos(0, 0, 0),
            detail={"profile": {"user": {"id": "u1"}, "profile": {"nombre": "Ana"}, "isAdmin": False}},
        )
        self.assertEqual(out["masHtml"], "")

    def test_admin_si_ve_la_tarjeta_de_admin(self):
        out = self._harness(
            fetch_impl=self._fetch_conteos(0, 0, 0),
            detail={"profile": {"user": {"id": "u1"}, "profile": {"nombre": "Ana"}, "isAdmin": True}},
        )
        self.assertIn("admin.html", out["masHtml"])

    def test_guarda_la_hora_de_ultima_carga_exitosa(self):
        out = self._harness(
            fetch_impl=self._fetch_conteos(1, 1, 1),
            detail={"profile": {"user": {"id": "u1"}, "profile": {"nombre": "Ana"}, "isAdmin": False}},
        )
        self.assertIsNotNone(out["ultimaCarga"])

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
