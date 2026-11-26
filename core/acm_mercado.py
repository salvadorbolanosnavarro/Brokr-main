"""Normalización de anuncios del mercado para el ACM.

Funciones puras (sin red ni base de datos): convierten un anuncio, venga de
donde venga (bloque estructurado de un portal, inventario de una cuenta,
EasyBroker), en la forma única con la que trabaja el ACM, y calculan la
"huella" que deduplica el mismo inmueble publicado en varios portales.

La matemática del análisis vive en ``core/acm_calculo.py``.
"""
from __future__ import annotations

import math
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urljoin, urlsplit, urlunsplit

FAMILIAS = ("casa", "departamento", "terreno", "local", "oficina", "bodega", "otro")
OPERACIONES = ("venta", "renta")

# Palabras que delatan el tipo de inmueble en el título de un anuncio.
_TIPO_PALABRAS = (
    ("departamento", ("departamento", "depto", "depa", "penthouse", "loft", "condominio vertical")),
    ("terreno", ("terreno", "lote ", "lotes", "predio", "rancho", "huerta")),
    ("local", ("local comercial", "local en", "locales", "local ")),
    ("oficina", ("oficina", "consultorio", "edificio")),
    ("bodega", ("bodega", "nave industrial", "nave ")),
    ("casa", ("casa", "residencia", "villa", "quinta", "townhouse")),
)

# Una banda de precio cubre ±12% (factor 1.25 entre bandas): un anuncio que
# baja 5-10% normalmente se queda en su banda; si cruza al vecino, la
# deduplicación lo busca también en las bandas contiguas (ver
# ``huellas_candidatas``).
_FACTOR_BANDA = 1.25
# Dos anuncios con los mismos atributos y precios a más de 25% de distancia
# se consideran inmuebles distintos, no un cambio de precio.
MAX_CAMBIO_PRECIO_MISMO_ANUNCIO = 0.25

_KV = re.compile(r"^([a-z0-9_]+)=(.*)$")
_LINEA_ANUNCIO = re.compile(r"^\s*\d+\)\s*(.+)$")


def normalizar(texto: Any) -> str:
    """Minúsculas, sin acentos ni signos, espacios simples."""
    s = unicodedata.normalize("NFKD", str(texto or ""))
    s = "".join(ch for ch in s if not unicodedata.combining(ch)).lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def numero(valor: Any) -> Optional[float]:
    """Convierte '3,450,000', '$ 3.4 mdp' o 120.5 en float; None si no hay número."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor) if math.isfinite(valor) and valor > 0 else None
    texto = str(valor).lower().replace(" ", " ").strip()
    if not texto:
        return None
    multiplicador = 1.0
    if re.search(r"\b(mdp|millones?|mill?\.?)\b", texto):
        multiplicador = 1_000_000.0
    texto = re.sub(r"[^0-9.,]", "", texto)
    if not texto:
        return None
    if texto.count(",") and texto.count("."):
        texto = texto.replace(",", "")
    elif texto.count(",") == 1 and len(texto.split(",")[1]) != 3:
        texto = texto.replace(",", ".")
    else:
        texto = texto.replace(",", "")
    if texto.count(".") > 1:
        texto = texto.replace(".", "")
    try:
        n = float(texto) * multiplicador
    except ValueError:
        return None
    return n if math.isfinite(n) and n > 0 else None


def coordenada(valor: Any, limite: float) -> Optional[float]:
    """Latitud (limite=90) o longitud (limite=180); admite negativos. 0 o
    fuera de rango = sin coordenada."""
    try:
        n = float(valor)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(n) or n == 0 or abs(n) > limite:
        return None
    return n


def entero(valor: Any) -> Optional[int]:
    n = numero(valor)
    return int(round(n)) if n is not None else None


def familia_tipo(tipo: Any, titulo: str = "") -> str:
    """Lleva cualquier tipo o subtipo a una de las 7 familias del catálogo."""
    t = normalizar(tipo)
    if t in FAMILIAS:
        return t
    try:
        from core.catalogo_inmuebles import tipo_familia

        fam = tipo_familia(str(tipo or ""))
        if fam:
            return fam
    except Exception:  # pragma: no cover - el catálogo siempre importa en producción
        pass
    # La palabra que aparece primero manda: "Casa cerca de local comercial"
    # es una casa, no un local.
    texto = f" {t} {normalizar(titulo)} "
    mejor, mejor_pos = "otro", None
    for familia, palabras in _TIPO_PALABRAS:
        for p in palabras:
            pos = texto.find(f" {p.strip()}")
            if pos >= 0 and (mejor_pos is None or pos < mejor_pos):
                mejor, mejor_pos = familia, pos
    return mejor


def operacion_de(valor: Any, titulo: str = "") -> Optional[str]:
    texto = f"{normalizar(valor)} {normalizar(titulo)}"
    if "renta" in texto or "alquiler" in texto or "arriendo" in texto:
        return "renta"
    if "venta" in texto or "vende" in texto or "preventa" in texto:
        return "venta"
    return None


def url_canonica(url: Any) -> str:
    texto = str(url or "").strip()
    if not texto.startswith(("http://", "https://")):
        return ""
    try:
        partes = urlsplit(texto)
        return urlunsplit((partes.scheme, partes.netloc.lower(), partes.path.rstrip("/"), "", ""))
    except ValueError:
        return ""


def _banda_precio(precio: float) -> int:
    return int(round(math.log(precio) / math.log(_FACTOR_BANDA)))


def _huella_base(c: Dict[str, Any]) -> str:
    def r(v: Any, paso: float) -> str:
        n = numero(v)
        return "" if n is None else str(int(round(n / paso)))

    return "|".join([
        normalizar(c.get("pais") or "MX"),
        normalizar(c.get("ciudad")),
        normalizar(c.get("colonia")),
        c.get("tipo") or "",
        c.get("operacion") or "",
        r(c.get("m2_construccion"), 2),
        r(c.get("m2_terreno"), 2),
        str(entero(c.get("recamaras")) or ""),
        str(numero(c.get("banos")) or ""),
    ])


def huella_comparable(c: Dict[str, Any]) -> str:
    """Llave que identifica al mismo inmueble aunque esté en varios portales:
    ubicación + tipo + operación + superficies + recámaras/baños + banda de
    precio. No usa la URL porque cada portal tiene la suya."""
    precio = numero(c.get("precio")) or 1.0
    return f"{_huella_base(c)}|b{_banda_precio(precio)}"


def huellas_candidatas(c: Dict[str, Any]) -> List[str]:
    """La huella propia y las de las dos bandas de precio vecinas: así una
    baja de precio que cruza de banda se reconoce como el mismo anuncio."""
    base = _huella_base(c)
    banda = _banda_precio(numero(c.get("precio")) or 1.0)
    return [f"{base}|b{banda}", f"{base}|b{banda - 1}", f"{base}|b{banda + 1}"]


def elegir_existente(nuevo: Dict[str, Any], existentes: Iterable[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Entre las filas con huella candidata, la del precio más cercano si está
    dentro del margen de un cambio de precio razonable."""
    precio = numero(nuevo.get("precio"))
    if not precio:
        return None
    candidatas = set(huellas_candidatas(nuevo))
    mejor, mejor_dif = None, None
    for fila in existentes:
        if fila.get("huella") not in candidatas:
            continue
        p = numero(fila.get("precio"))
        if not p:
            continue
        dif = abs(p - precio) / p
        if dif <= MAX_CAMBIO_PRECIO_MISMO_ANUNCIO and (mejor_dif is None or dif < mejor_dif):
            mejor, mejor_dif = fila, dif
    return mejor


def es_util(c: Dict[str, Any]) -> bool:
    """Un comparable sin precio, sin operación o sin ninguna superficie no
    sirve para comparar precio/m²."""
    if not numero(c.get("precio")) or c.get("operacion") not in OPERACIONES:
        return False
    return bool(numero(c.get("m2_construccion")) or numero(c.get("m2_terreno")))


def _moneda(valor: Any, por_defecto: str) -> str:
    t = normalizar(valor)
    if t in ("usd", "us", "dolares", "dlls", "dls", "us dolares") or "dolar" in t:
        return "USD"
    if t in ("mxn", "mxp", "pesos", "mn", "peso"):
        return "MXN"
    if t and len(t) == 3 and t.isalpha():
        return t.upper()
    return por_defecto


def comparable_desde_anuncio(
    anuncio: Dict[str, Any],
    *,
    url_pagina: str = "",
    portal: str = "",
    zona: Optional[Dict[str, Any]] = None,
    moneda_defecto: str = "MXN",
) -> Optional[Dict[str, Any]]:
    """Convierte un anuncio extraído de un portal en un comparable normalizado.

    ``zona`` aporta lo que la búsqueda ya sabe (colonia, ciudad, estado, país,
    tipo y operación buscados) cuando el anuncio no lo dice.
    """
    zona = zona or {}
    titulo = str(anuncio.get("titulo") or "").strip()[:200]
    operacion = operacion_de(anuncio.get("operacion"), titulo) or zona.get("operacion")
    tipo = familia_tipo(anuncio.get("tipo"), titulo)
    if tipo == "otro" and zona.get("tipo"):
        tipo = zona["tipo"]
    liga = str(anuncio.get("url") or "").strip()
    if liga and url_pagina and not liga.startswith(("http://", "https://")):
        liga = urljoin(url_pagina, liga)
    ubicacion = str(anuncio.get("ubicacion") or "")
    colonia = zona.get("colonia") or ""
    if ubicacion and zona.get("colonia") and normalizar(zona["colonia"]) not in normalizar(ubicacion):
        # El anuncio dice otra ubicación: se guarda la primera parte (suele
        # ser la colonia) para no atribuirlo a la colonia buscada.
        colonia = ubicacion.split(",")[0].strip()[:120] or colonia
    c = {
        "fuente": "portal",
        "portal": portal or None,
        "url": url_canonica(liga) or url_canonica(url_pagina) or None,
        "titulo": titulo or None,
        "tipo": tipo,
        "operacion": operacion,
        "precio": numero(anuncio.get("precio")),
        "moneda": _moneda(anuncio.get("moneda"), moneda_defecto),
        "m2_construccion": numero(anuncio.get("m2_construccion")),
        "m2_terreno": numero(anuncio.get("m2_terreno")),
        "recamaras": entero(anuncio.get("recamaras")),
        "banos": numero(anuncio.get("banos")),
        "estacionamientos": entero(anuncio.get("estacionamientos")),
        "antiguedad": entero(anuncio.get("antiguedad")),
        "colonia": colonia or None,
        "ciudad": zona.get("ciudad") or None,
        "estado": zona.get("estado") or None,
        "pais": zona.get("pais") or "MX",
        "foto_url": url_canonica(anuncio.get("foto_url")) or None,
    }
    # Un "precio" de renta de 3 dígitos en venta o al revés suele ser precio
    # por m² o un error de captura: fuera.
    if c["precio"] and c["operacion"] == "venta" and c["precio"] < 50_000 and c["moneda"] == "MXN":
        return None
    return c if es_util(c) else None


def parse_anuncios_estructurados(page_text: str) -> List[Dict[str, Any]]:
    """Lee el bloque «ANUNCIOS ESTRUCTURADOS DE LA PÁGINA» que arma
    ``routers/avm_websearch._formatea_estructurado_firecrawl``: una línea por
    anuncio, ``titulo | ubicacion | clave=valor | ...``. No necesita IA."""
    if not page_text or "ANUNCIOS ESTRUCTURADOS" not in page_text:
        return []
    bloque = page_text.split("ANUNCIOS ESTRUCTURADOS", 1)[1]
    anuncios: List[Dict[str, Any]] = []
    for linea in bloque.splitlines()[1:]:
        m = _LINEA_ANUNCIO.match(linea)
        if not m:
            if anuncios and not linea.strip():
                break
            continue
        anuncio: Dict[str, Any] = {}
        libres: List[str] = []
        for parte in m.group(1).split(" | "):
            parte = parte.strip()
            kv = _KV.match(parte)
            if kv:
                anuncio[kv.group(1)] = kv.group(2).strip()
            elif parte:
                libres.append(parte)
        if libres:
            anuncio["titulo"] = libres[0]
        if len(libres) > 1:
            anuncio["ubicacion"] = libres[1]
        if anuncio.get("precio"):
            anuncios.append(anuncio)
    return anuncios


def comparable_desde_propiedad(p: Dict[str, Any], *, origen: str) -> Optional[Dict[str, Any]]:
    """Inmueble de la tabla ``propiedades`` (inventario de la cuenta o bolsa)
    en forma de comparable. Nunca copia datos del propietario."""
    fotos = p.get("fotos") or []
    foto = None
    if isinstance(fotos, list) and fotos:
        primera = fotos[0]
        foto = primera.get("url") if isinstance(primera, dict) else primera
    lat, lng = coordenada(p.get("lat"), 90), coordenada(p.get("lng"), 180)
    c = {
        "id": f"{origen}-{p.get('id')}",
        "origen": origen,
        "titulo": (p.get("titulo") or "")[:200] or None,
        "url": None,
        "portal": "Inventario de la cuenta" if origen == "inventario" else "Bolsa Broquer",
        "tipo": familia_tipo(p.get("tipo") or p.get("subtipo")),
        "operacion": "renta" if str(p.get("operacion") or "").startswith("renta") else "venta",
        "precio": numero(p.get("precio")),
        "moneda": (p.get("moneda") or "MXN").upper(),
        "m2_construccion": numero(p.get("m2_construccion")),
        "m2_terreno": numero(p.get("m2_terreno")),
        "recamaras": entero(p.get("recamaras")),
        "banos": numero(p.get("banos")),
        "estacionamientos": entero(p.get("estacionamientos")),
        "antiguedad": entero(p.get("antiguedad")),
        "colonia": p.get("colonia"),
        "ciudad": p.get("ciudad"),
        "estado": p.get("estado"),
        "lat": lat if lat is not None and lng is not None else None,
        "lng": lng if lat is not None and lng is not None else None,
        "precision_ubicacion": "exacta" if lat is not None and lng is not None else "colonia",
        "foto_url": foto if isinstance(foto, str) and foto.startswith("https://") else None,
        "publicada_en": p.get("publicada_en") or p.get("created_at"),
        "estatus": "activo",
    }
    return c if es_util(c) else None
