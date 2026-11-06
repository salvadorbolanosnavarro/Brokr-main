"""Validación central de archivos subidos o importados a Broquer.

Única puerta para decidir si un archivo se puede guardar. Todos los puntos de
subida (backend, importaciones de terceros como EasyBroker y medios de
WhatsApp) llaman a ``validar_archivo`` con el perfil de su módulo.

Reglas:
  * Lista blanca por módulo (``PERFILES``): cada módulo acepta solo lo que
    necesita y con su tamaño máximo.
  * El tipo real se decide por los primeros bytes del archivo. La extensión y
    el Content-Type que manda el navegador NO cuentan para aceptar.
  * Se rechazan HTML, HTM, SVG, XML, JS, MHTML, ejecutables y cualquier tipo
    que no esté en la lista blanca, también cuando vienen "disfrazados"
    (``WhatsApp.html`` renombrado a ``.pdf``) o con doble extensión
    (``foto.jpg.html``).
  * El nombre interno siempre es un UUID con la extensión del tipo real. El
    nombre original solo se guarda como dato, ya sanitizado.

El espejo de estas reglas para el navegador vive en ``archivos-seguros.js``;
debe mantenerse alineado (lo revisa ``tests/test_file_validation.py``).
"""
from __future__ import annotations

import io
import re
import unicodedata
import uuid
import zipfile
from dataclasses import dataclass


MB = 1024 * 1024

# ── Tipos conocidos: clave → (mime canónico, extensión canónica, extensiones aceptadas)
TIPOS: dict[str, tuple[str, str, frozenset[str]]] = {
    "jpg": ("image/jpeg", "jpg", frozenset({"jpg", "jpeg", "jfif", "jpe"})),
    "png": ("image/png", "png", frozenset({"png"})),
    "webp": ("image/webp", "webp", frozenset({"webp"})),
    "gif": ("image/gif", "gif", frozenset({"gif"})),
    "heic": ("image/heic", "heic", frozenset({"heic", "heif"})),
    "pdf": ("application/pdf", "pdf", frozenset({"pdf"})),
    "mp4": ("video/mp4", "mp4", frozenset({"mp4", "m4v"})),
    "mov": ("video/quicktime", "mov", frozenset({"mov", "qt"})),
    "3gp": ("video/3gpp", "3gp", frozenset({"3gp", "3gpp"})),
    "webm": ("video/webm", "webm", frozenset({"webm", "weba"})),
    "ogg": ("audio/ogg", "ogg", frozenset({"ogg", "oga", "opus"})),
    "mp3": ("audio/mpeg", "mp3", frozenset({"mp3"})),
    "m4a": ("audio/mp4", "m4a", frozenset({"m4a", "aac"})),
    "aac": ("audio/aac", "aac", frozenset({"aac"})),
    "amr": ("audio/amr", "amr", frozenset({"amr"})),
    "wav": ("audio/wav", "wav", frozenset({"wav"})),
    "docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document", "docx",
             frozenset({"docx", "dotx"})),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx",
             frozenset({"xlsx"})),
    "pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "pptx",
             frozenset({"pptx"})),
    "doc": ("application/msword", "doc", frozenset({"doc"})),
    "xls": ("application/vnd.ms-excel", "xls", frozenset({"xls"})),
    "ppt": ("application/vnd.ms-powerpoint", "ppt", frozenset({"ppt"})),
    "zip": ("application/zip", "zip", frozenset({"zip"})),
    "txt": ("text/plain", "txt", frozenset({"txt"})),
    "csv": ("text/csv", "csv", frozenset({"csv"})),
}

# Extensiones que jamás se aceptan, estén donde estén en el nombre
# (``foto.jpg.html`` y ``foto.html.jpg`` se rechazan igual).
EXTENSIONES_PELIGROSAS = frozenset({
    "html", "htm", "xhtml", "xht", "shtml", "mhtml", "mht", "webarchive", "eml",
    "svg", "svgz", "xml", "xsl", "xslt", "rss", "atom",
    "js", "mjs", "cjs", "jsx", "ts", "tsx", "vbs", "vbe", "wsf", "wsh", "hta",
    "exe", "msi", "bat", "cmd", "com", "scr", "pif", "cpl", "dll", "sys", "lnk", "reg",
    "sh", "bash", "zsh", "ps1", "psm1", "jar", "apk", "app", "dmg", "pkg", "deb", "rpm",
    "php", "phtml", "php3", "php4", "php5", "phar", "asp", "aspx", "jsp", "cgi", "pl", "py", "rb",
    "swf", "url", "iso", "svc", "htaccess",
})

# Content-Types que nunca deben quedar guardados (se ejecutarían como página).
MIMES_PELIGROSOS = frozenset({
    "text/html", "application/xhtml+xml", "image/svg+xml", "text/xml", "application/xml",
    "text/javascript", "application/javascript", "application/x-javascript", "application/ecmascript",
    "text/ecmascript", "message/rfc822", "multipart/related", "application/x-mimearchive",
    "text/x-component", "application/x-msdownload", "application/x-sh", "application/x-httpd-php",
    "application/hta", "text/vbscript", "application/x-shockwave-flash",
})

_IMAGENES = ("jpg", "png", "webp", "gif", "heic")
_OFFICE = ("docx", "xlsx", "pptx", "doc", "xls", "ppt")
_AUDIO = ("ogg", "mp3", "m4a", "aac", "amr", "wav")
_VIDEO = ("mp4", "mov", "3gp", "webm")


@dataclass(frozen=True)
class Perfil:
    tipos: tuple[str, ...]
    max_bytes: int
    descripcion: str  # lo que se le dice al usuario: "fotos JPG, PNG o WebP"


# Lista blanca por módulo. Si un módulo necesita algo nuevo se agrega AQUÍ.
PERFILES: dict[str, Perfil] = {
    # Público: fotos que salen en fichas y micrositios.
    "foto_propiedad": Perfil(_IMAGENES, 25 * MB, "fotos JPG, PNG, WebP, GIF o HEIC"),
    "foto_importada": Perfil(("jpg", "png", "webp", "gif"), 25 * MB, "fotos JPG, PNG, WebP o GIF"),
    "documento_propiedad": Perfil(("pdf", "jpg", "png", "webp"), 15 * MB, "PDF o fotos JPG, PNG o WebP"),
    # Privado: adjuntos de la bitácora de contactos, clientes, inmuebles y tareas.
    "adjunto_historial": Perfil(_IMAGENES + ("pdf",) + _VIDEO + _OFFICE + ("zip", "txt", "csv"), 25 * MB,
                                "fotos, videos, PDF, Word, Excel, PowerPoint, ZIP o texto"),
    # Privado: firma electrónica, expedientes PLD, finanzas.
    "firma_documento": Perfil(("pdf", "docx"), 20 * MB, "PDF o Word (.docx)"),
    "identificacion": Perfil(("jpg", "png", "webp", "heic"), 8 * MB, "fotos JPG, PNG, WebP o HEIC"),
    "expediente_pld": Perfil(("jpg", "png", "webp", "heic", "pdf"), 10 * MB, "fotos (JPG, PNG, WebP) o PDF"),
    "comprobante": Perfil(("jpg", "png", "webp", "heic", "pdf"), 10 * MB, "fotos (JPG, PNG, WebP) o PDF"),
    "ticket_ia": Perfil(("jpg", "png", "webp", "pdf"), 10 * MB, "fotos (JPG, PNG, WebP) o PDF"),
    "machote": Perfil(("docx",), 12 * MB, "archivos Word (.docx)"),
    "soporte_captura": Perfil(_IMAGENES, 5 * MB, "imágenes JPG, PNG, WebP, GIF o HEIC"),
    "imagen_editor": Perfil(("jpg", "png", "webp", "heic"), 12 * MB, "imágenes JPG, PNG, WebP o HEIC"),
    # Privado: lo que mandan los prospectos por WhatsApp (límite de Meta: 100 MB).
    "whatsapp_media": Perfil(_IMAGENES + ("pdf",) + _VIDEO + _AUDIO + _OFFICE + ("zip", "txt", "csv"), 100 * MB,
                             "fotos, videos, audios, PDF o documentos de Office"),
    # Generado por Broquer (videos de fichas): solo se verifica que sea MP4.
    "video_generado": Perfil(("mp4",), 500 * MB, "videos MP4"),
}


class ArchivoRechazado(ValueError):
    """El archivo no se puede guardar. ``mensaje`` va tal cual al usuario."""

    def __init__(self, mensaje: str, status_code: int = 415):
        super().__init__(mensaje)
        self.mensaje = mensaje
        self.status_code = status_code


@dataclass(frozen=True)
class ArchivoValidado:
    tipo: str             # clave en TIPOS
    mime: str             # Content-Type canónico con el que se guarda
    extension: str        # extensión canónica del tipo real
    tamano: int
    nombre_original: str  # sanitizado; solo para mostrar
    nombre_interno: str   # <uuid>.<extension>; usar como nombre en Storage

    @property
    def es_imagen(self) -> bool:
        return self.tipo in _IMAGENES

    @property
    def se_muestra_en_linea(self) -> bool:
        """Imágenes, video, audio y PDF se pueden abrir en el navegador; lo demás se descarga."""
        return self.tipo in _IMAGENES + _VIDEO + _AUDIO + ("pdf",)


# ── Detección por contenido ───────────────────────────────────────────────

_MARCAS_MARKUP = (
    b"<!doctype", b"<html", b"<head", b"<body", b"<script", b"<svg", b"<?xml", b"<iframe",
    b"<object", b"<embed", b"<meta", b"<link", b"<style", b"<img", b"<a ", b"<div", b"<form",
    b"<base", b"<xml", b"<xsl", b"javascript:", b"mime-version:", b"content-type: multipart",
)


def parece_markup(contenido: bytes) -> bool:
    """True si el inicio del archivo parece HTML/SVG/XML/MHTML (aunque diga ser otra cosa)."""
    cabeza = contenido[:4096]
    for bom in (b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff"):
        if cabeza.startswith(bom):
            cabeza = cabeza[len(bom):]
            break
    # UTF-16: quita los ceros intercalados para poder buscar etiquetas.
    if cabeza[:200].count(b"\x00") > 40:
        cabeza = cabeza.replace(b"\x00", b"")
    cabeza = cabeza.lower()
    return any(marca in cabeza for marca in _MARCAS_MARKUP)


def _tipo_iso_bmff(contenido: bytes) -> str | None:
    if len(contenido) < 12 or contenido[4:8] != b"ftyp":
        return None
    marca = contenido[8:12]
    if marca in (b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"mif1", b"msf1", b"avif"):
        return "heic" if marca != b"avif" else None
    if marca == b"qt  ":
        return "mov"
    if marca in (b"M4A ", b"M4B ", b"M4P "):
        return "m4a"
    if marca.startswith(b"3g"):
        return "3gp"
    return "mp4"


def _tipo_zip(contenido: bytes) -> str:
    try:
        with zipfile.ZipFile(io.BytesIO(contenido)) as z:
            nombres = set(z.namelist())
    except Exception:
        return "zip_invalido"
    if "[Content_Types].xml" in nombres:
        if any(n.startswith("word/") for n in nombres):
            return "docx"
        if any(n.startswith("xl/") for n in nombres):
            return "xlsx"
        if any(n.startswith("ppt/") for n in nombres):
            return "pptx"
    return "zip"


def _es_texto_plano(contenido: bytes) -> bool:
    muestra = contenido[:65536]
    if b"\x00" in muestra:
        return False
    try:
        muestra.decode("utf-8")
        return True
    except UnicodeDecodeError as exc:
        # Un corte a la mitad de un carácter al final de la muestra no cuenta.
        if exc.start >= len(muestra) - 4:
            return True
    try:
        muestra.decode("cp1252")
        return True
    except UnicodeDecodeError:
        return False


def detectar_tipo(contenido: bytes, extension: str = "") -> str | None:
    """Tipo real según los primeros bytes; ``None`` si no se reconoce.

    ``extension`` solo se usa para desempatar formatos que comparten firma
    (Word/Excel/PowerPoint antiguos, TXT/CSV); nunca para aceptar algo cuyo
    contenido no coincide.
    """
    c = contenido or b""
    if c.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if c.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if c[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if c[:4] == b"RIFF" and c[8:12] == b"WEBP":
        return "webp"
    if c[:4] == b"RIFF" and c[8:12] == b"WAVE":
        return "wav"
    if c.startswith(b"%PDF-"):
        return "pdf"
    iso = _tipo_iso_bmff(c)
    if iso:
        return iso
    if c.startswith(b"\x1a\x45\xdf\xa3"):
        return "webm"
    if c.startswith(b"OggS"):
        return "ogg"
    if c.startswith(b"#!AMR"):
        return "amr"
    if c.startswith(b"ID3") or (len(c) > 1 and c[0] == 0xFF and c[1] in (0xFB, 0xF3, 0xF2, 0xFA)):
        return "mp3"
    if len(c) > 1 and c[0] == 0xFF and c[1] in (0xF1, 0xF9):
        return "aac"
    if c.startswith(b"PK\x03\x04"):
        return _tipo_zip(c)
    if c.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return extension if extension in ("doc", "xls", "ppt") else "ole"
    if c and _es_texto_plano(c) and not parece_markup(c):
        return "csv" if extension == "csv" else "txt"
    return None


# ── Nombres ───────────────────────────────────────────────────────────────

def extensiones_de(nombre: str) -> list[str]:
    """Todas las "extensiones" del nombre: ``a.tar.gz`` → ``['tar', 'gz']``."""
    base = re.split(r"[\\/]", nombre or "")[-1].strip().strip(".")
    partes = base.split(".")
    return [p.strip().lower() for p in partes[1:] if p.strip()]


def nombre_peligroso(nombre: str) -> bool:
    return any(ext in EXTENSIONES_PELIGROSAS for ext in extensiones_de(nombre))


def sanitizar_nombre(nombre: str | None, *, por_defecto: str = "archivo", max_len: int = 120) -> str:
    """Nombre original apto para mostrarse: sin rutas, controles ni caracteres raros."""
    base = re.split(r"[\\/]", str(nombre or ""))[-1]
    base = unicodedata.normalize("NFKC", base)
    base = "".join(ch for ch in base if unicodedata.category(ch)[0] != "C")
    base = re.sub(r"[^\w .,()\[\]+@#&-]+", "_", base, flags=re.UNICODE)
    base = re.sub(r"\s+", " ", base).strip(" ._")
    if not base:
        return por_defecto
    if len(base) > max_len:
        raiz, punto, ext = base.rpartition(".")
        if punto and 0 < len(ext) <= 8:
            base = raiz[: max_len - len(ext) - 1] + "." + ext
        else:
            base = base[:max_len]
    return base


def nombre_interno(extension: str) -> str:
    ext = re.sub(r"[^a-z0-9]", "", (extension or "").lower())[:8] or "bin"
    return f"{uuid.uuid4().hex}.{ext}"


# ── Validación ────────────────────────────────────────────────────────────

def _texto_mb(n: int) -> str:
    return f"{n // MB} MB" if n >= MB else f"{max(1, n // 1024)} KB"


def validar_archivo(
    contenido: bytes,
    nombre: str | None,
    perfil: str,
    *,
    content_type: str | None = None,  # solo informativo: nunca decide
) -> ArchivoValidado:
    """Valida un archivo contra el perfil de su módulo o lanza ``ArchivoRechazado``."""
    if perfil not in PERFILES:
        raise ValueError(f"Perfil de archivo desconocido: {perfil}")
    regla = PERFILES[perfil]
    nombre = nombre or ""
    rechazo = f"Ese tipo de archivo no está permitido aquí. Solo se aceptan {regla.descripcion}."

    if not contenido:
        raise ArchivoRechazado("El archivo llegó vacío. Vuelve a seleccionarlo.", 400)
    if len(contenido) > regla.max_bytes:
        raise ArchivoRechazado(
            f"El archivo pesa más de {_texto_mb(regla.max_bytes)}. Sube uno más ligero.", 413)
    if nombre_peligroso(nombre):
        raise ArchivoRechazado(
            "Por seguridad no se aceptan páginas web (HTML), SVG, scripts ni programas, "
            "aunque tengan otra extensión. " + rechazo.split(". ", 1)[1])
    if (content_type or "").split(";")[0].strip().lower() in MIMES_PELIGROSOS:
        raise ArchivoRechazado(rechazo)

    exts = extensiones_de(nombre)
    ext = exts[-1] if exts else ""
    tipo = detectar_tipo(contenido, ext)
    if tipo is None or tipo not in regla.tipos or tipo not in TIPOS:
        raise ArchivoRechazado(rechazo)

    mime, ext_canonica, _ = TIPOS[tipo]
    # Texto (TXT/CSV): además se exige que la extensión lo diga; un "texto" sin
    # extensión clara suele ser otra cosa renombrada.
    if tipo in ("txt", "csv") and ext not in ("txt", "csv"):
        raise ArchivoRechazado(rechazo)

    return ArchivoValidado(
        tipo=tipo,
        mime=mime,
        extension=ext_canonica,
        tamano=len(contenido),
        nombre_original=sanitizar_nombre(nombre, por_defecto=f"archivo.{ext_canonica}"),
        nombre_interno=nombre_interno(ext_canonica),
    )


_EXT_EN_LINEA = frozenset(
    ext for clave in _IMAGENES + _VIDEO + _AUDIO + ("pdf",) for ext in TIPOS[clave][2]
)


def se_abre_en_linea(ruta: str) -> bool:
    """¿El archivo guardado en ``ruta`` se puede abrir en el navegador?

    Lo que no sea imagen, video, audio o PDF se entrega como descarga
    (``Content-Disposition: attachment``), incluido cualquier archivo viejo con
    extensión riesgosa.
    """
    exts = extensiones_de(ruta.rsplit("/", 1)[-1])
    return bool(exts) and exts[-1] in _EXT_EN_LINEA and not nombre_peligroso(ruta)


def tipo_guardable(content_type: str | None, ruta: str) -> bool:
    """Última barrera antes de escribir en Storage (la usa ``core.storage``)."""
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct in MIMES_PELIGROSOS:
        return False
    if ct.startswith("text/") and ct not in ("text/plain", "text/csv"):
        return False
    if ct.endswith("+xml"):
        return False
    return not nombre_peligroso(ruta.rsplit("/", 1)[-1])


async def leer_upload(archivo, perfil: str) -> tuple[bytes, ArchivoValidado]:
    """Lee un ``UploadFile`` sin pasar del máximo del perfil y lo valida.

    Convierte ``ArchivoRechazado`` en ``HTTPException`` con el mensaje en español.
    """
    from fastapi import HTTPException

    limite = PERFILES[perfil].max_bytes
    contenido = await archivo.read(limite + 1)
    try:
        validado = validar_archivo(contenido, getattr(archivo, "filename", None), perfil,
                                   content_type=getattr(archivo, "content_type", None))
    except ArchivoRechazado as exc:
        raise HTTPException(exc.status_code, exc.mensaje) from None
    return contenido, validado


# ── Visibilidad de adjuntos ───────────────────────────────────────────────

def solo_publicos(adjuntos) -> list[dict]:
    """Adjuntos que pueden salir en una ficha pública, bolsa o micrositio.

    Regla: todo adjunto nuevo nace con ``publico: false`` y solo se publica con
    una acción explícita del agente. Los que existían antes de esta regla no
    tienen la marca y se respetan como públicos para no romper fichas.
    Además se descarta cualquier liga que no sea https o que apunte a un
    archivo con extensión riesgosa (HTML, SVG, etc.).
    """
    salida = []
    for a in adjuntos or []:
        if not isinstance(a, dict) or a.get("publico") is False:
            continue
        url = str(a.get("url") or "")
        if not url.startswith("https://") or nombre_peligroso(url.split("?", 1)[0]):
            continue
        salida.append(a)
    return salida
