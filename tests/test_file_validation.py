"""Archivos seguros: nada subido a Broquer puede quedar como página web pública.

Cubre el incidente de referencia (una copia de WhatsApp Web .html subida como
adjunto y servida en una liga pública) y sus variantes: doble extensión, HTML
renombrado, SVG con script, imports de terceros, medios de WhatsApp, ligas
firmadas que caducan, aislamiento entre cuentas y fichas públicas.
"""
from __future__ import annotations

import asyncio
import io
import json
import re
import shutil
import subprocess
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from fastapi import HTTPException, UploadFile
from starlette.datastructures import Headers

import core.file_validation as fv
import core.storage as storage


ROOT = Path(__file__).resolve().parents[1]
NODE = shutil.which("node")

WHATSAPP_HTML = (b"<!DOCTYPE html><html><head><title>WhatsApp</title></head><body>"
                 b"<div class='chat'>Cliente: mi INE es ...</div><script>window.x=1</script></body></html>")
SVG_SCRIPT = (b'<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg">'
              b'<script>alert(document.cookie)</script></svg>')
MHTML = b"MIME-Version: 1.0\r\nContent-Type: multipart/related; boundary=x\r\n\r\n--x\r\n"
PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>"
       b"endobj\n3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 612 792]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")


def _jpg() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8), (200, 30, 30)).save(buf, format="JPEG")
    return buf.getvalue()


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (8, 8)).save(buf, format="PNG")
    return buf.getvalue()


def _docx() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", "<w:document/>")
    return buf.getvalue()


JPG = _jpg()


def _upload(datos: bytes, nombre: str, tipo: str) -> UploadFile:
    return UploadFile(io.BytesIO(datos), filename=nombre, headers=Headers({"content-type": tipo}))


# ═════════════════════════════════════════════════════════════════════════
# 1) Validación central
# ═════════════════════════════════════════════════════════════════════════

class RechazosTests(unittest.TestCase):
    """Lo del incidente y sus variantes se rechaza en TODOS los módulos."""

    PERFILES = list(fv.PERFILES)

    def _rechaza(self, datos, nombre, tipo=None):
        for perfil in self.PERFILES:
            with self.subTest(perfil=perfil, nombre=nombre):
                with self.assertRaises(fv.ArchivoRechazado) as cm:
                    fv.validar_archivo(datos, nombre, perfil, content_type=tipo)
                self.assertTrue(cm.exception.mensaje)
                self.assertNotIn("Traceback", cm.exception.mensaje)

    def test_rechaza_whatsapp_html(self):
        self._rechaza(WHATSAPP_HTML, "WhatsApp.html", "text/html")
        self._rechaza(WHATSAPP_HTML, "WhatsApp Web - Chat.htm", "text/html")

    def test_rechaza_doble_extension(self):
        # Contenido de foto real, pero nombre con .html al final: no se acepta.
        self._rechaza(JPG, "foto.jpg.html", "image/jpeg")
        # Y al revés: .html escondido antes de la extensión "buena".
        self._rechaza(JPG, "foto.html.jpg", "image/jpeg")

    def test_rechaza_html_renombrado_a_pdf(self):
        self._rechaza(WHATSAPP_HTML, "contrato.pdf", "application/pdf")
        self._rechaza(WHATSAPP_HTML, "foto.jpg", "image/jpeg")
        self._rechaza(b"\xef\xbb\xbf  <html><body>x</body></html>", "notas.txt", "text/plain")
        self._rechaza(WHATSAPP_HTML.decode().encode("utf-16"), "notas.txt", "text/plain")

    def test_rechaza_svg_con_script(self):
        self._rechaza(SVG_SCRIPT, "logo.svg", "image/svg+xml")
        self._rechaza(SVG_SCRIPT, "logo.png", "image/png")

    def test_rechaza_mhtml_xml_js_y_ejecutables(self):
        self._rechaza(MHTML, "WhatsApp.mhtml", "multipart/related")
        self._rechaza(b"<?xml version='1.0'?><a/>", "datos.xml", "application/xml")
        self._rechaza(b"alert(1)", "app.js", "text/javascript")
        self._rechaza(b"MZ\x90\x00" + b"\x00" * 64, "factura.exe", "application/octet-stream")
        self._rechaza(b"MZ\x90\x00" + b"\x00" * 64, "factura.pdf", "application/pdf")

    def test_el_content_type_del_navegador_no_decide(self):
        # Decir "image/jpeg" no convierte un HTML en foto.
        with self.assertRaises(fv.ArchivoRechazado):
            fv.validar_archivo(WHATSAPP_HTML, "foto", "foto_propiedad", content_type="image/jpeg")
        # Y un Content-Type peligroso basta para rechazar aunque los bytes sean de foto.
        with self.assertRaises(fv.ArchivoRechazado):
            fv.validar_archivo(JPG, "foto.jpg", "foto_propiedad", content_type="text/html")

    def test_lista_blanca_por_modulo_y_tamano(self):
        with self.assertRaises(fv.ArchivoRechazado):  # un PDF no es foto de inmueble
            fv.validar_archivo(PDF, "plano.pdf", "foto_propiedad")
        with self.assertRaises(fv.ArchivoRechazado):  # un Word no es identificación
            fv.validar_archivo(_docx(), "ine.docx", "identificacion")
        grande = JPG + b"\x00" * (fv.PERFILES["soporte_captura"].max_bytes + 1)
        with self.assertRaises(fv.ArchivoRechazado) as cm:
            fv.validar_archivo(grande, "captura.jpg", "soporte_captura")
        self.assertEqual(cm.exception.status_code, 413)
        with self.assertRaises(fv.ArchivoRechazado) as cm:
            fv.validar_archivo(b"", "vacio.jpg", "foto_propiedad")
        self.assertEqual(cm.exception.status_code, 400)

    def test_mensajes_en_espanol(self):
        with self.assertRaises(fv.ArchivoRechazado) as cm:
            fv.validar_archivo(WHATSAPP_HTML, "WhatsApp.html", "adjunto_historial")
        self.assertIn("Por seguridad no se aceptan páginas web (HTML)", cm.exception.mensaje)
        with self.assertRaises(fv.ArchivoRechazado) as cm:
            fv.validar_archivo(WHATSAPP_HTML, "contrato.pdf", "documento_propiedad")
        self.assertIn("Solo se aceptan PDF o fotos", cm.exception.mensaje)


class AceptadosTests(unittest.TestCase):
    def test_acepta_jpg_legitimo(self):
        v = fv.validar_archivo(JPG, "IMG_2041.JPG", "foto_propiedad", content_type="image/jpeg")
        self.assertEqual((v.tipo, v.mime, v.extension), ("jpg", "image/jpeg", "jpg"))
        self.assertRegex(v.nombre_interno, r"^[0-9a-f]{32}\.jpg$")
        self.assertEqual(v.nombre_original, "IMG_2041.JPG")

    def test_acepta_pdf_legitimo(self):
        for perfil in ("documento_propiedad", "adjunto_historial", "firma_documento",
                       "expediente_pld", "comprobante"):
            with self.subTest(perfil=perfil):
                v = fv.validar_archivo(PDF, "Escritura final.pdf", perfil, content_type="application/pdf")
                self.assertEqual((v.mime, v.extension), ("application/pdf", "pdf"))
                self.assertTrue(v.nombre_interno.endswith(".pdf"))

    def test_tipo_real_aunque_el_navegador_mienta(self):
        # Foto de iPhone que llega sin tipo: decide el contenido.
        v = fv.validar_archivo(_png(), "foto", "foto_propiedad", content_type="")
        self.assertEqual(v.mime, "image/png")

    def test_office_y_texto_en_adjuntos(self):
        self.assertEqual(fv.validar_archivo(_docx(), "contrato.docx", "adjunto_historial").tipo, "docx")
        self.assertEqual(fv.validar_archivo(b"nombre,telefono\nAna,555\n", "lista.csv",
                                            "adjunto_historial").mime, "text/csv")

    def test_nombre_original_sanitizado(self):
        v = fv.validar_archivo(JPG, "../../etc/<img src=x onerror=alert(1)>.jpg", "foto_propiedad")
        self.assertNotIn("/", v.nombre_original)
        self.assertNotIn("<", v.nombre_original)
        self.assertNotIn(">", v.nombre_original)


class LeerUploadTests(unittest.TestCase):
    def test_upload_rechazado_es_http_415_en_espanol(self):
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(fv.leer_upload(_upload(WHATSAPP_HTML, "WhatsApp.html", "text/html"), "expediente_pld"))
        self.assertEqual(cm.exception.status_code, 415)
        self.assertIn("seguridad", cm.exception.detail)

    def test_upload_valido(self):
        datos, v = asyncio.run(fv.leer_upload(_upload(PDF, "ine.pdf", "application/pdf"), "expediente_pld"))
        self.assertEqual(datos, PDF)
        self.assertEqual(v.mime, "application/pdf")


# ═════════════════════════════════════════════════════════════════════════
# 2) Última barrera en Storage y cómo se sirven los archivos
# ═════════════════════════════════════════════════════════════════════════

class _Resp:
    def __init__(self, status=200, data=None):
        self.status_code, self._data = status, data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._data


class _Http:
    llamadas: list = []
    respuesta = _Resp(200, {})

    def __init__(self, *a, **k):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def post(self, url, headers=None, content=None, json=None):
        _Http.llamadas.append({"url": url, "headers": headers or {}, "json": json, "content": content})
        return _Http.respuesta


def _cfg():
    return SimpleNamespace(supabase_url="https://sb.test", supabase_service_key="svc",
                           require_supabase_service=lambda: None, require_supabase_public=lambda: None)


class StorageTests(unittest.TestCase):
    def setUp(self):
        _Http.llamadas = []
        _Http.respuesta = _Resp(200, {})
        self.p = [mock.patch.object(storage, "settings", _cfg()),
                  mock.patch.object(storage.httpx, "AsyncClient", _Http)]
        for p in self.p:
            p.start()

    def tearDown(self):
        for p in self.p:
            p.stop()

    def test_nunca_guarda_html_svg_ni_scripts(self):
        for ruta, tipo in (("a/WhatsApp.html", "image/jpeg"), ("a/x.jpg", "text/html"),
                           ("a/logo.svg", "image/png"), ("a/x.png", "image/svg+xml"),
                           ("a/foto.jpg.html", "image/jpeg"), ("a/x.bin", "application/javascript"),
                           ("a/x.xml", "application/xml")):
            with self.subTest(ruta=ruta, tipo=tipo):
                with self.assertRaises(ValueError):
                    asyncio.run(storage.upload_object("adjuntos-historial", ruta, b"x", content_type=tipo))
        self.assertEqual(_Http.llamadas, [])

    def test_xml_del_servidor_solo_en_bucket_privado(self):
        asyncio.run(storage.upload_object("pld-expedientes", "u/avisos/a.xml", b"<a/>",
                                          content_type="application/xml", server_generated_xml=True))
        with self.assertRaises(ValueError):
            asyncio.run(storage.upload_object("fotos-propiedades", "a.xml", b"<a/>",
                                              content_type="application/xml", server_generated_xml=True))

    def test_privado_sin_cache_publica(self):
        asyncio.run(storage.upload_object("firmas", "u/d/original.pdf", PDF, content_type="application/pdf"))
        self.assertEqual(_Http.llamadas[-1]["headers"]["cache-control"], "private, no-store, max-age=0")
        asyncio.run(storage.upload_object("wa-media", "u/c/1-a.jpg", JPG, content_type="image/jpeg"))
        self.assertIn("no-store", _Http.llamadas[-1]["headers"]["cache-control"])
        # Las fotos públicas conservan el caché por defecto de Supabase.
        asyncio.run(storage.upload_object("fotos-propiedades", "a.jpg", JPG, content_type="image/jpeg"))
        self.assertNotIn("cache-control", _Http.llamadas[-1]["headers"])

    def test_ligas_firmadas_caducan(self):
        _Http.respuesta = _Resp(200, {"signedURL": "/object/sign/firmas/u/a.pdf?token=t"})
        url = asyncio.run(storage.create_signed_object_url("firmas", "u/a.pdf", expires_in=300))
        self.assertEqual(_Http.llamadas[-1]["json"], {"expiresIn": 300})
        self.assertEqual(url, "https://sb.test/storage/v1/object/sign/firmas/u/a.pdf?token=t")
        for malo in (0, -5, None, 3.5, "3600"):
            with self.subTest(expires_in=malo):
                with self.assertRaises(ValueError):
                    asyncio.run(storage.create_signed_object_url("firmas", "u/a.pdf", expires_in=malo))
                with self.assertRaises(ValueError):
                    asyncio.run(storage.create_signed_object_urls("firmas", ["u/a.pdf"], expires_in=malo))

    def test_descarga_forzada_para_lo_que_no_se_abre_en_linea(self):
        _Http.respuesta = _Resp(200, {"signedURL": "/object/sign/b/x.docx?token=t"})
        url = asyncio.run(storage.create_signed_object_url("adjuntos-historial", "x.docx",
                                                           expires_in=60, download=True))
        self.assertTrue(url.endswith("?token=t&download="))
        _Http.respuesta = _Resp(200, [
            {"path": "u/c/1-a.jpg", "signedURL": "/object/sign/wa-media/u/c/1-a.jpg?token=1", "error": None},
            {"path": "u/c/2-b.docx", "signedURL": "/object/sign/wa-media/u/c/2-b.docx?token=2", "error": None},
            {"path": "u/c/3-c.pdf", "signedURL": None, "error": "not found"},
        ])
        firmadas = asyncio.run(storage.create_signed_object_urls(
            "wa-media", ["u/c/1-a.jpg", "u/c/2-b.docx", "u/c/3-c.pdf"], expires_in=3600,
            download_for={"u/c/2-b.docx"}))
        self.assertEqual(_Http.llamadas[-1]["json"]["expiresIn"], 3600)
        self.assertFalse(firmadas["u/c/1-a.jpg"].endswith("download="))
        self.assertTrue(firmadas["u/c/2-b.docx"].endswith("&download="))
        self.assertNotIn("u/c/3-c.pdf", firmadas)

    def test_se_abre_en_linea(self):
        for ruta in ("a.jpg", "u/c/1-x.pdf", "x.mp4", "a.ogg"):
            self.assertTrue(fv.se_abre_en_linea(ruta), ruta)
        for ruta in ("a.docx", "x.zip", "WhatsApp.html", "a.svg", "foto.jpg.html", "sin-extension"):
            self.assertFalse(fv.se_abre_en_linea(ruta), ruta)


class NosniffTests(unittest.TestCase):
    def test_api_responde_con_nosniff(self):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from core.security_headers import instalar_cabeceras_seguras

        app = FastAPI()
        instalar_cabeceras_seguras(app)

        @app.get("/x")
        async def _x():
            return {"ok": True}

        r = TestClient(app).get("/x")
        self.assertEqual(r.headers.get("x-content-type-options"), "nosniff")

    def test_main_instala_cabeceras(self):
        main = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("instalar_cabeceras_seguras(app)", main)


# ═════════════════════════════════════════════════════════════════════════
# 3) Puntos de subida del backend usan la validación central
# ═════════════════════════════════════════════════════════════════════════

class PuntosDeSubidaTests(unittest.TestCase):
    def test_todos_los_endpoints_de_subida_validan(self):
        esperados = {
            "routers/firmas.py": ['leer_upload(archivo, "firma_documento")', 'leer_upload(archivo, "identificacion")'],
            "routers/cumplimiento.py": ['leer_upload(archivo, "expediente_pld")'],
            "routers/finanzas.py": ['leer_upload(archivo, "comprobante")', 'leer_upload(archivo, "ticket_ia")'],
            "routers/soporte.py": ['"soporte_captura"'],
            "routers/machotes.py": ['"machote"'],
            "routers/image_cleaner.py": ['"imagen_editor"'],
            "routers/whatsapp_media_storage.py": ['"whatsapp_media"', "copiar_foto_a_inventario"],
            "core/property_photos.py": ['"foto_importada"', "fetch_public_bytes"],
            "migrar_fotos.py": ['"foto_propiedad"'],
        }
        for ruta, fragmentos in esperados.items():
            fuente = (ROOT / ruta).read_text(encoding="utf-8")
            for f in fragmentos:
                with self.subTest(archivo=ruta, fragmento=f):
                    self.assertIn(f, fuente)

    def test_nombres_internos_no_usan_el_nombre_del_usuario(self):
        cump = (ROOT / "routers/cumplimiento.py").read_text(encoding="utf-8")
        fin = (ROOT / "routers/finanzas.py").read_text(encoding="utf-8")
        self.assertIn("{val.nombre_interno}", cump)
        self.assertIn("{val.nombre_interno}", fin)
        self.assertNotIn("{_limpio(archivo.filename)}\"", cump)

    def test_pld_rechaza_html_disfrazado(self):
        import routers.cumplimiento as c
        subir = mock.AsyncMock()
        with mock.patch.object(c, "upload_object", subir):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(c._subir("u1", "e1", "ine", _upload(WHATSAPP_HTML, "ine.pdf", "application/pdf"),
                                     "cliente"))
        self.assertEqual(cm.exception.status_code, 415)
        subir.assert_not_called()


class WhatsAppMediaTests(unittest.TestCase):
    def test_documento_html_de_un_prospecto_no_se_guarda(self):
        import routers.whatsapp_media_storage as wm
        subir = mock.AsyncMock(return_value="https://sb/x")
        with mock.patch.object(wm, "upload_object", subir):
            url, ruta = asyncio.run(wm.guardar_archivo("u1", "c1", WHATSAPP_HTML, "text/html", "WhatsApp.html"))
        self.assertEqual((url, ruta), (None, None))
        subir.assert_not_called()

    def test_foto_legitima_se_guarda_con_uuid_y_tipo_real(self):
        import routers.whatsapp_media_storage as wm
        subir = mock.AsyncMock(return_value="https://sb/x")
        with mock.patch.object(wm, "upload_object", subir):
            url, ruta = asyncio.run(wm.guardar_archivo("u1", "c1", JPG, "application/octet-stream", "foto"))
        self.assertEqual(url, "https://sb/x")
        self.assertRegex(ruta, r"^u1/c1/\d+-[0-9a-f]{32}\.jpg$")
        self.assertEqual(subir.call_args.kwargs["content_type"], "image/jpeg")

    def test_bandeja_entrega_ligas_firmadas(self):
        import routers.whatsapp_media_storage as wm
        mensajes = [
            {"id": 1, "media_path": "u1/c1/1-a.jpg", "media_url": "https://sb/storage/v1/object/public/wa-media/u1/c1/1-a.jpg"},
            {"id": 2, "media_path": None, "media_url": "https://sb/storage/v1/object/public/wa-media/u1/c1/old.pdf"},
            {"id": 3, "media_path": None, "media_url": None, "body": "hola"},
        ]
        firmar = mock.AsyncMock(return_value={"u1/c1/1-a.jpg": "https://firmada/1", "u1/c1/old.pdf": "https://firmada/2"})
        with mock.patch.object(wm, "create_signed_object_urls", firmar):
            asyncio.run(wm.firmar_medios(mensajes))
        self.assertEqual([m["media_url"] for m in mensajes], ["https://firmada/1", "https://firmada/2", None])
        self.assertEqual(firmar.call_args.kwargs["expires_in"], wm.MEDIA_SEGUNDOS)
        self.assertLessEqual(wm.MEDIA_SEGUNDOS, 3600)

    def test_una_cuenta_no_ve_medios_de_otra(self):
        """Solo se firman medios de mensajes que la consulta limitada a la cuenta regresó."""
        import routers.whatsapp_inbox_read as ir
        consultas = []

        async def sb_get(tabla, params):
            consultas.append(params)
            return []  # la conversación es de otra cuenta: no hay filas visibles

        async def require_user(_r):
            return "u-intruso"

        async def ids_visibles(uid):
            return [uid]

        firmar = mock.AsyncMock(return_value={})
        with mock.patch("routers.whatsapp_media_storage.create_signed_object_urls", firmar):
            res = asyncio.run(ir.wa2_mensajes_list_core(
                object(), "conv-de-otra-cuenta", _require_user=require_user, _ids_visibles=ids_visibles,
                _in_filter=lambda ids: "in.(" + ",".join(ids) + ")", sb_get=sb_get))
        self.assertEqual(res["mensajes"], [])
        self.assertEqual(consultas[0]["user_id"], "in.(u-intruso)")
        firmar.assert_not_called()

    def test_sin_sesion_no_hay_medios(self):
        import routers.whatsapp_inbox_read as ir

        async def require_user(_r):
            raise HTTPException(401, "Sesión requerida.")

        sb_get = mock.AsyncMock()
        with self.assertRaises(HTTPException) as cm:
            asyncio.run(ir.wa2_mensajes_list_core(object(), "c1", _require_user=require_user,
                                                  _ids_visibles=mock.AsyncMock(), _in_filter=str, sb_get=sb_get))
        self.assertEqual(cm.exception.status_code, 401)
        sb_get.assert_not_called()

    def test_fotos_de_whatsapp_se_copian_al_inventario(self):
        import routers.whatsapp_media_storage as wm
        with mock.patch("core.storage.download_object", mock.AsyncMock(return_value=JPG)), \
             mock.patch("core.storage.upload_object", mock.AsyncMock(return_value="https://sb/fotos/x.jpg")) as up:
            url = asyncio.run(wm.publicar_foto("u1/c1/1-a.jpg"))
        self.assertEqual(url, "https://sb/fotos/x.jpg")
        self.assertEqual(up.call_args.args[0], "fotos-propiedades")
        brain = (ROOT / "routers/whatsapp_prospect_brain.py").read_text(encoding="utf-8")
        self.assertIn("publicar_foto(f.get(\"media_path\"))", brain)
        self.assertNotIn('fotos = [f["media_url"]', brain)


class RescateFotosTests(unittest.TestCase):
    def test_copia_fotos_ligadas_a_chats_y_actualiza_el_inmueble(self):
        import core.property_photos as pp
        base = "https://sb.test/storage/v1/object/public/"
        filas = [
            {"id": "p1", "fotos": [base + "fotos-propiedades/ok.jpg", base + "wa-media/u/c/1-a.jpg"]},
            {"id": "p2", "fotos": [base + "fotos-propiedades/b.jpg"]},
            {"id": "p3", "fotos": [base + "adjuntos-historial/x.html"]},  # no es foto: se deja, no se copia
        ]
        descargas = {"u/c/1-a.jpg": JPG, "x.html": WHATSAPP_HTML}
        parches = []

        async def get_rows(tabla, params, timeout=None):
            return filas if params["offset"] == "0" else []

        async def patch_rows(tabla, params, payload, timeout=None):
            parches.append((params["id"], payload["fotos"]))

        with mock.patch("core.database.get_rows", get_rows), mock.patch("core.database.patch_rows", patch_rows), \
             mock.patch("core.storage.settings", _cfg()), \
             mock.patch("core.storage.download_object", mock.AsyncMock(side_effect=lambda b, r, **k: descargas[r])), \
             mock.patch("core.storage.upload_object", mock.AsyncMock(return_value=base + "fotos-propiedades/nueva.jpg")), \
             mock.patch("core.storage.delete_object", mock.AsyncMock(side_effect=AssertionError("no borra"))):
            res = asyncio.run(pp.rescatar_fotos_de_buckets_de_clientes())
        self.assertEqual(res, {"inmuebles": 1, "fotos_copiadas": 1, "fotos_no_copiadas": 1})
        self.assertEqual(parches, [("eq.p1", [base + "fotos-propiedades/ok.jpg", base + "fotos-propiedades/nueva.jpg"])])

    def test_boton_solo_admin(self):
        import routers.admin_archivos as aa
        with mock.patch.object(aa, "require_admin", mock.AsyncMock(side_effect=HTTPException(403, "x"))), \
             mock.patch.object(aa, "rescatar_fotos_de_buckets_de_clientes", mock.AsyncMock()) as r:
            with self.assertRaises(HTTPException):
                asyncio.run(aa.copiar_fotos_de_clientes(object()))
        r.assert_not_called()


class ImportacionesTests(unittest.TestCase):
    def test_easybroker_no_guarda_html_disfrazado_de_foto(self):
        import core.property_photos as pp
        with mock.patch("core.http.fetch_public_bytes", mock.AsyncMock(return_value=WHATSAPP_HTML)), \
             mock.patch("core.storage.upload_object", mock.AsyncMock()) as up:
            self.assertIsNone(asyncio.run(pp.importar_foto_externa("https://eb.example/foto.jpg")))
        up.assert_not_called()

    def test_easybroker_foto_valida_con_uuid(self):
        import core.property_photos as pp
        with mock.patch("core.http.fetch_public_bytes", mock.AsyncMock(return_value=JPG)), \
             mock.patch("core.storage.upload_object", mock.AsyncMock(return_value="https://sb/x.jpg")) as up:
            self.assertEqual(asyncio.run(pp.importar_foto_externa("https://eb.example/a.php?id=1")), "https://sb/x.jpg")
        bucket, nombre = up.call_args.args[:2]
        self.assertEqual(bucket, "fotos-propiedades")
        self.assertRegex(nombre, r"^[0-9a-f]{32}\.jpg$")
        self.assertEqual(up.call_args.kwargs["content_type"], "image/jpeg")

    def test_easybroker_bloquea_direcciones_internas(self):
        import core.property_photos as pp
        with mock.patch("core.storage.upload_object", mock.AsyncMock()) as up:
            self.assertIsNone(asyncio.run(pp.importar_foto_externa("http://169.254.169.254/latest/meta-data")))
        up.assert_not_called()


# ═════════════════════════════════════════════════════════════════════════
# 4) Adjuntos del historial: otra cuenta / sin sesión
# ═════════════════════════════════════════════════════════════════════════

class AdjuntosAislamientoTests(unittest.TestCase):
    URL = "https://sb.test/storage/v1/object/public/adjuntos-historial/0f1e2d3c4b5a69788796a5b4c3d2e1f0.docx"

    def _correr(self, visibles, token="tok"):
        import routers.adjuntos_ligas as al

        class Cliente:
            async def get(self, url, headers=None, params=None):
                tabla = url.rsplit("/", 1)[-1]
                return SimpleNamespace(status_code=200, json=lambda: [{"id": 1}] if tabla in visibles else [])

            async def __aenter__(self):
                return self

            async def __aexit__(self, *a):
                return False

        firmar = mock.AsyncMock(return_value="https://firmada")
        req = SimpleNamespace(headers={"authorization": f"Bearer {token}"} if token else {})
        with mock.patch.object(al, "require_user_id", mock.AsyncMock(return_value="u1")), \
             mock.patch.object(al.httpx, "AsyncClient", lambda **kw: Cliente()), \
             mock.patch.object(al, "rest_url", lambda t: f"https://sb.test/rest/v1/{t}"), \
             mock.patch.object(al, "create_signed_object_url", firmar):
            res = asyncio.run(al.adjuntos_ligas(al.LigasReq(urls=[self.URL]), req))
        return res, firmar

    def test_otra_cuenta_no_obtiene_liga(self):
        res, firmar = self._correr(visibles=())
        self.assertIsNone(res["ligas"][self.URL])
        firmar.assert_not_called()

    def test_sin_sesion_no_hay_liga(self):
        import routers.adjuntos_ligas as al
        with mock.patch.object(al, "require_user_id", mock.AsyncMock(side_effect=HTTPException(401, "x"))):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(al.adjuntos_ligas(al.LigasReq(urls=[self.URL]), SimpleNamespace(headers={})))
        self.assertEqual(cm.exception.status_code, 401)

    def test_word_se_entrega_como_descarga(self):
        res, firmar = self._correr(visibles=("actividades",))
        self.assertEqual(res["ligas"][self.URL], "https://firmada")
        self.assertIs(firmar.call_args.kwargs["download"], True)
        self.assertLessEqual(firmar.call_args.kwargs["expires_in"], 3600)


class ComprobantesAislamientoTests(unittest.TestCase):
    def test_otra_cuenta_no_puede_pedir_el_comprobante(self):
        import routers.finanzas as f
        consultas = []

        async def sb_get(tabla, params):
            consultas.append(params)
            return []  # el movimiento no es de esta cuenta

        firmar = mock.AsyncMock()
        with mock.patch.object(f, "_uid", mock.AsyncMock(return_value="u-intruso")), \
             mock.patch.object(f, "_sb_get", sb_get), mock.patch.object(f, "create_signed_object_url", firmar):
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(f.liga_comprobante(object(), "mov-de-otro"))
        self.assertEqual(cm.exception.status_code, 404)
        self.assertEqual(consultas[0]["user_id"], "eq.u-intruso")
        firmar.assert_not_called()


# ═════════════════════════════════════════════════════════════════════════
# 5) Fichas públicas: siguen mostrando fotos; documentos solo si son públicos
# ═════════════════════════════════════════════════════════════════════════

class FichasPublicasTests(unittest.TestCase):
    PROP = {
        "id": "p1", "titulo": "Casa en Coyoacán", "tipo": "casa", "operacion": "venta", "precio": 4500000,
        "fotos": ["https://sb.test/storage/v1/object/public/fotos-propiedades/prop_a.jpg",
                  "https://sb.test/storage/v1/object/public/fotos-propiedades/prop_b.webp"],
        "documentos": [
            {"nombre": "Plano viejo.pdf", "url": "https://sb.test/storage/v1/object/public/documentos-publicos/o/a.pdf"},
            {"nombre": "Escrituras.pdf", "url": "https://sb.test/storage/v1/object/public/documentos-publicos/o/b.pdf",
             "publico": False},
            {"nombre": "Lista de precios.pdf", "url": "https://sb.test/storage/v1/object/public/documentos-publicos/o/c.pdf",
             "publico": True},
            {"nombre": "WhatsApp.html", "url": "https://sb.test/storage/v1/object/public/documentos-publicos/o/WhatsApp.html"},
        ],
    }

    def test_ficha_publica_muestra_fotos_y_solo_documentos_publicos(self):
        from core.sitio_render import ficha
        html = ficha(dict(self.PROP), "/s/demo", None, False, "")
        for foto in self.PROP["fotos"]:
            self.assertIn(foto, html)
        self.assertIn("Plano viejo.pdf", html)        # existente sin marca: sigue público
        self.assertIn("Lista de precios.pdf", html)   # publicado a propósito
        self.assertNotIn("Escrituras.pdf", html)      # privado
        self.assertNotIn("WhatsApp.html", html)       # riesgoso: nunca

    def test_bolsa_muestra_fotos_y_solo_documentos_publicos(self):
        from routers.bolsa import _publica
        fila = _publica(dict(self.PROP), {}, "otro")
        self.assertEqual(fila["fotos"], self.PROP["fotos"])
        self.assertEqual([d["nombre"] for d in fila["documentos"]], ["Plano viejo.pdf", "Lista de precios.pdf"])

    def test_documento_nuevo_nace_privado_y_publicar_pide_aviso(self):
        js = (ROOT / "propiedades-plus.js").read_text(encoding="utf-8")
        self.assertIn("publico: false", js)
        self.assertIn("AVISO_PUBLICO", js)
        self.assertIn("confirm(aviso", js)
        seg = (ROOT / "archivos-seguros.js").read_text(encoding="utf-8")
        self.assertIn("Este archivo será visible para cualquier persona con la liga.", seg)


# ═════════════════════════════════════════════════════════════════════════
# 6) Navegador: archivos-seguros.js es espejo del backend
# ═════════════════════════════════════════════════════════════════════════

class FrontendEspejoTests(unittest.TestCase):
    JS = (ROOT / "archivos-seguros.js").read_text(encoding="utf-8")

    def test_mismas_extensiones_peligrosas(self):
        m = re.search(r"var PELIGROSAS = \(([\s\S]*?)\)\.split", self.JS)
        js = set(" ".join(re.findall(r"'([^']*)'", m.group(1))).split())
        self.assertEqual(js, set(fv.EXTENSIONES_PELIGROSAS))

    def test_mismos_limites_que_el_backend(self):
        for perfil in ("foto_propiedad", "documento_propiedad", "adjunto_historial"):
            m = re.search(perfil + r": \{[\s\S]*?max: (\d+) \* MB", self.JS)
            self.assertEqual(int(m.group(1)) * fv.MB, fv.PERFILES[perfil].max_bytes, perfil)

    def test_subidas_directas_pasan_por_el_validador(self):
        for ruta, perfil in (("propiedades-editor.js", "foto_propiedad"), ("ficha-manual.html", "foto_propiedad"),
                             ("mi-sitio.html", "foto_propiedad"), ("mi-sitio-web.js", "foto_propiedad"),
                             ("video.html", "foto_propiedad"), ("propiedades-plus.js", "documento_propiedad"),
                             ("historial-adjuntos.js", "adjunto_historial")):
            fuente = (ROOT / ruta).read_text(encoding="utf-8")
            with self.subTest(archivo=ruta):
                self.assertIn(f"validar(", fuente)
                self.assertIn(f"'{perfil}'", fuente)
                # Ya no se usa el tipo que dice el navegador para subir.
                self.assertNotIn("'Content-Type': file.type", fuente)
                self.assertNotIn("'Content-Type':contentType", fuente)

    @unittest.skipUnless(NODE, "node no está disponible en este entorno")
    def test_validador_del_navegador(self):
        casos = [
            ("WhatsApp.html", WHATSAPP_HTML, "adjunto_historial", False),
            ("foto.jpg.html", JPG, "foto_propiedad", False),
            ("contrato.pdf", WHATSAPP_HTML, "documento_propiedad", False),
            ("logo.svg", SVG_SCRIPT, "foto_propiedad", False),
            ("logo.png", SVG_SCRIPT, "foto_propiedad", False),
            ("IMG_1.jpg", JPG, "foto_propiedad", True),
            ("Plano.pdf", PDF, "documento_propiedad", True),
            ("contrato.docx", _docx(), "adjunto_historial", True),
        ]
        payload = json.dumps([[n, list(b), p, ok] for n, b, p, ok in casos])
        script = (
            "globalThis.window = globalThis; globalThis.crypto = require('crypto').webcrypto;\n"
            + self.JS + "\n"
            + "const casos = " + payload + ";\n"
            + "(async () => { const out = [];\n"
            + "  for (const [n, b, p, ok] of casos) {\n"
            + "    const u8 = new Uint8Array(b);\n"
            + "    const f = { name: n, size: u8.length, slice: (a, z) => ({ arrayBuffer: async () => u8.slice(a, z).buffer }) };\n"
            + "    let r; try { const v = await bkArchivos.validar(f, p); r = [true, v.mime, v.nombreInterno]; }\n"
            + "    catch (e) { r = [false, e.message]; }\n"
            + "    out.push([n, ok, r]); }\n"
            + "  console.log(JSON.stringify(out)); })();\n"
        )
        proc = subprocess.run([NODE, "-e", script], capture_output=True, text=True, timeout=20)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for nombre, esperado, res in json.loads(proc.stdout):
            with self.subTest(nombre=nombre):
                self.assertEqual(res[0], esperado, res)
                if esperado:
                    self.assertRegex(res[2], r"^[0-9a-f]{32}\.[a-z0-9]+$")
                else:
                    self.assertTrue(res[1])  # mensaje en español para el usuario


# ═════════════════════════════════════════════════════════════════════════
# 7) Reporte de archivos existentes (solo lectura)
# ═════════════════════════════════════════════════════════════════════════

class ReporteTests(unittest.TestCase):
    def test_motivos(self):
        from core.reporte_archivos import motivos_de
        self.assertTrue(motivos_de("adjuntos-historial", "123_ab.html", "text/html", bucket_publico=True))
        self.assertTrue(motivos_de("fotos-propiedades", "prop_x.jpg.html", "image/jpeg", bucket_publico=True))
        self.assertTrue(motivos_de("fotos-propiedades", "prop_x.svg", "image/svg+xml", bucket_publico=True))
        m = motivos_de("wa-media", "u/c/1-a.jpg", "image/jpeg", bucket_publico=True)
        self.assertEqual(m, ["archivo de cliente en bucket PÚBLICO (se abre con la liga, sin sesión)"])
        self.assertEqual(motivos_de("wa-media", "u/c/1-a.jpg", "image/jpeg", bucket_publico=False), [])
        self.assertEqual(motivos_de("fotos-propiedades", "prop_x.jpg", "image/jpeg", bucket_publico=True), [])

    def test_reporte_solo_lee(self):
        """No abre ni descarga contenido, no borra: solo lista nombres/metadatos."""
        import core.reporte_archivos as ra

        async def list_buckets():
            return [{"id": "adjuntos-historial", "public": True}, {"id": "fotos-propiedades", "public": True}]

        async def list_objects(bucket, prefijo="", **kw):
            if kw.get("offset"):
                return []
            return {"adjuntos-historial": [{"id": "1", "name": "17_ab.html", "metadata": {"mimetype": "text/html"}}],
                    "fotos-propiedades": [{"id": "2", "name": "prop_a.jpg", "metadata": {"mimetype": "image/jpeg"}}]}[bucket]

        async def get_rows(tabla, params, timeout=None):
            if tabla == "actividades" and params.get("offset") == "0":
                return [{"id": 1, "org_id": "org-1", "adjuntos": [
                    {"url": "https://sb/storage/v1/object/public/adjuntos-historial/17_ab.html"}]}]
            return []

        prohibidos = mock.AsyncMock(side_effect=AssertionError("el reporte no debe descargar ni borrar"))
        with mock.patch.object(ra, "list_buckets", list_buckets), mock.patch.object(ra, "list_objects", list_objects), \
             mock.patch.object(ra, "get_rows", get_rows), mock.patch.object(ra, "settings", _cfg()), \
             mock.patch.object(storage, "download_object", prohibidos), \
             mock.patch.object(storage, "delete_object", prohibidos), \
             mock.patch.object(storage, "delete_objects", prohibidos):
            filas, resumen = asyncio.run(ra.construir(avisar=lambda *_: None))
        self.assertEqual(len(filas), 1)
        self.assertEqual(filas[0]["cuenta"], "org-1")
        self.assertEqual(filas[0]["ruta"], "17_ab.html")
        self.assertIn("extensión riesgosa", filas[0]["motivo"])
        self.assertEqual(resumen["revisados"], {"adjuntos-historial": 1, "fotos-propiedades": 1})
        self.assertEqual(ra.a_csv(filas).splitlines()[0], "cuenta,bucket,ruta,motivo")

    def test_endpoint_solo_admin(self):
        import routers.admin_archivos as aa
        with mock.patch.object(aa, "require_admin", mock.AsyncMock(side_effect=HTTPException(403, "Acceso denegado."))), \
             mock.patch.object(aa, "construir", mock.AsyncMock()) as c:
            with self.assertRaises(HTTPException) as cm:
                asyncio.run(aa.reporte_archivos(object()))
        self.assertEqual(cm.exception.status_code, 403)
        c.assert_not_called()


if __name__ == "__main__":
    unittest.main()
