"""El backend de /images/clean SIEMPRE entrega la imagen editada como JPEG
o PNG (ver routers/image_cleaner.py) — nunca en el formato original, ni
para un HEIC de iPhone. Si el nombre del archivo descargado conserva la
extensión ORIGINAL (".heic"/".HEIC"), el resultado queda con bytes de JPEG
pero nombre de HEIC: Fotos, Windows, o cualquier app que decida el formato
por la extensión en vez del contenido real, lo tratan mal o lo rechazan.

Estas pruebas ejecutan de verdad (con Node) las funciones de
image-cleaner.html que arman ese nombre, en vez de solo buscar texto en el
archivo — así una regresión futura en la lógica se detecta aquí y no en
producción.
"""
import re
import shutil
import subprocess
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
HTML = ROOT / "image-cleaner.html"
NODE = shutil.which("node")


def _extraer_funcion(source: str, nombre: str) -> str:
    inicio = source.index(f"function {nombre}(")
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


class ImageCleanerDownloadFilenameTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not NODE:
            raise unittest.SkipTest("node no está disponible en este entorno")
        html = HTML.read_text(encoding="utf-8")
        m = re.search(r"<script>([\s\S]*?)</script>", html)
        script = m.group(1)
        cls.funcs = "\n".join(
            _extraer_funcion(script, nombre)
            for nombre in ("extensionEditada", "nombreArchivoEditado", "pareceImagen")
        )

    def _node(self, js_body: str) -> str:
        proc = subprocess.run(
            [NODE, "-e", self.funcs + "\n" + js_body],
            capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def test_heic_de_iphone_se_descarga_como_jpg_no_heic(self):
        out = self._node("console.log(nombreArchivoEditado('IMG_1234.HEIC', 'image/jpeg'))")
        self.assertEqual(out, "IMG_1234_editada.jpg")

    def test_heic_minuscula_tambien_se_normaliza(self):
        out = self._node("console.log(nombreArchivoEditado('foto.heic', 'image/jpeg'))")
        self.assertEqual(out, "foto_editada.jpg")

    def test_png_de_entrada_conserva_extension_png(self):
        out = self._node("console.log(nombreArchivoEditado('logo.png', 'image/png'))")
        self.assertEqual(out, "logo_editada.png")

    def test_jpeg_de_entrada_se_normaliza_a_jpg(self):
        out = self._node("console.log(nombreArchivoEditado('foto.jpeg', 'image/jpeg'))")
        self.assertEqual(out, "foto_editada.jpg")

    def test_pareceImagen_acepta_heic_sin_mime_type(self):
        # Chrome/Edge en Windows no reconocen HEIC y mandan file.type vacío.
        out = self._node("console.log(pareceImagen({ type: '', name: 'IMG_1234.HEIC' }))")
        self.assertEqual(out, "true")

    def test_pareceImagen_rechaza_no_imagenes_sin_mime_type(self):
        out = self._node("console.log(pareceImagen({ type: '', name: 'contrato.pdf' }))")
        self.assertEqual(out, "false")

    def test_pareceImagen_acepta_mime_type_normal(self):
        out = self._node("console.log(pareceImagen({ type: 'image/png', name: 'x' }))")
        self.assertEqual(out, "true")

    def test_no_quedan_usos_de_la_extension_original_del_archivo(self):
        source = HTML.read_text(encoding="utf-8")
        self.assertNotIn("orig.split('.').pop()", source)
        self.assertNotIn("n.split('.').pop()", source)

    def test_files_compile(self):
        # node --check valida sintaxis pura sin necesitar el DOM del
        # navegador (que este script sí toca fuera de las funciones de
        # arriba) — suficiente para atrapar un error de JS al editar.
        import tempfile
        html = HTML.read_text(encoding="utf-8")
        m = re.search(r"<script>([\s\S]*?)</script>", html)
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as f:
            f.write(m.group(1))
            ruta = f.name
        try:
            proc = subprocess.run([NODE, "--check", ruta], capture_output=True, text=True, timeout=10)
        finally:
            Path(ruta).unlink(missing_ok=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)


if __name__ == "__main__":
    unittest.main()
