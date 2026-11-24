"""Ingesta diaria de anuncios a avm_listings.

Reutiliza el scraper del AVM actual (routers/avm_websearch.py): la misma
llamada a Firecrawl con extracción estructurada, que deja en page_text un
bloque "ANUNCIOS ESTRUCTURADOS DE LA PÁGINA" con un anuncio por línea. Esta
ingesta:
  1. convierte lo que ya hay en avm_scrape_cache (mismo formato) en anuncios;
  2. lee las páginas de resultados de los portales de cada ciudad activa;
  3. geocodifica, calcula H3, inserta/actualiza por URL y registra cambios de
     precio en avm_price_history;
  4. marca fecha_baja a los anuncios que llevan 14 días sin aparecer;
  5. corre limpieza y duplicados sobre todo lo vivo y guarda el resultado.
"""
from __future__ import annotations

import asyncio
import logging
import re
from datetime import date, datetime, timedelta, timezone

import pandas as pd

from .. import geo
from .. import settings as S

log = logging.getLogger("broquer.avm_v2.ingesta")
DIAS_BAJA = 14
PAGINAS_POR_TIPO = 3
TIPO_PORTAL = {"casa": ("casas", "casas"), "depto": ("departamentos", "departamentos"),
               "terreno": ("terrenos", "terrenos"), "local": ("locales-comerciales", "locales-comerciales")}
MARCA = "ANUNCIOS ESTRUCTURADOS DE LA PÁGINA"
RE_LINEA = re.compile(r"^\s*\d+\)\s*(.+)$")
RE_TIPO = [("depto", re.compile(r"departamento|depto|\bpent ?house|loft", re.I)),
           ("terreno", re.compile(r"terreno|lote\b", re.I)),
           ("local", re.compile(r"\blocal\b|comercial", re.I)),
           ("casa", re.compile(r"\bcasa|residencia|townhouse|duplex", re.I))]
PORTALES = {"inmuebles24.com": "inmuebles24", "vivanuncios.com.mx": "vivanuncios", "lamudi.com.mx": "lamudi",
            "propiedades.com": "propiedades", "easybroker.com": "easybroker", "mercadolibre.com.mx": "mercadolibre"}


def fuente_de(url: str) -> str:
    for dom, nombre in PORTALES.items():
        if dom in url:
            return nombre
    return re.sub(r"^https?://(www\.)?", "", url).split("/")[0][:40]


def _num(v) -> float | None:
    try:
        x = float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None
    return x if x > 0 else None


def parsear_bloque(page_text: str, tipo_hint: str | None = None) -> list[dict]:
    """Lee el bloque estructurado que produce _formatea_estructurado_firecrawl
    ("titulo | ubicacion | precio=... | m2_construccion=... | url=...")."""
    if not page_text or MARCA not in page_text:
        return []
    bloque = page_text.split(MARCA, 1)[1]
    out = []
    for linea in bloque.splitlines()[1:]:
        m = RE_LINEA.match(linea)
        if not m:
            if linea.strip() == "":
                break
            continue
        partes = [p.strip() for p in m.group(1).split(" | ")]
        kv = {}
        libres = []
        for p in partes:
            if "=" in p and p.split("=", 1)[0].isidentifier():
                k, v = p.split("=", 1)
                kv[k] = v
            else:
                libres.append(p)
        url = kv.get("url", "")
        precio = _num(kv.get("precio"))
        if not url.startswith("http") or not precio:
            continue
        titulo = libres[0] if libres else ""
        tipo = tipo_hint
        for t, rx in RE_TIPO:
            if rx.search(titulo):
                tipo = t
                break
        operacion = "renta" if "renta" in (kv.get("operacion", "") + titulo).lower() else "venta"
        out.append({
            "url": url.split("?")[0], "fuente": fuente_de(url), "tipo": tipo, "operacion": operacion,
            "precio": precio, "moneda": (kv.get("moneda") or "MXN").upper().replace("$", "").strip() or "MXN",
            "m2_construidos": _num(kv.get("m2_construccion")), "m2_terreno": _num(kv.get("m2_terreno")),
            "recamaras": _num(kv.get("recamaras")), "banos": _num(kv.get("banos")),
            "estacionamientos": _num(kv.get("estacionamientos")),
            "ubicacion": libres[1] if len(libres) > 1 else "", "titulo": titulo,
        })
    return [a for a in out if a["tipo"]]


RE_JSONLD = re.compile(r"DATO ESTRUCTURADO JSON-LD \(alta confianza\): (.+)")


def parsear_json_ld(page_text: str, url: str, tipo_hint: str | None) -> list[dict]:
    """Páginas leídas sin Firecrawl traen el resumen JSON-LD del portal. Solo
    se usa si la página es el detalle de UN anuncio (un único bloque con
    precio y superficie): en listados no hay forma segura de separar datos."""
    bloques = RE_JSONLD.findall(page_text or "")
    if len(bloques) != 1 or not url.startswith("http"):
        return []
    kv = {}
    for parte in bloques[0].split("; "):
        if "=" in parte:
            k, v = parte.split("=", 1)
            kv[k.strip()] = v.strip()
    precio_txt = kv.get("precio", "")
    moneda = "USD" if "USD" in precio_txt.upper() else "MXN"
    precio = _num(precio_txt.split(" ")[0]) if precio_txt else None
    sup = _num(kv.get("superficie"))
    if not precio or not sup:
        return []
    nombre = kv.get("nombre", "")
    tipo = tipo_hint
    for t, rx in RE_TIPO:
        if rx.search(nombre):
            tipo = t
            break
    if not tipo:
        return []
    return [{
        "url": url.split("?")[0], "fuente": fuente_de(url), "tipo": tipo,
        "operacion": "renta" if "renta" in nombre.lower() else "venta", "precio": precio, "moneda": moneda,
        "m2_construidos": None if tipo == "terreno" else sup, "m2_terreno": sup if tipo == "terreno" else None,
        "recamaras": None, "banos": None, "estacionamientos": None,
        "ubicacion": kv.get("direccion", ""), "titulo": nombre,
    }]


def urls_portal(ciudad: dict, tipo: str, paginas: int = PAGINAS_POR_TIPO) -> list[str]:
    out = []
    i24, viv = TIPO_PORTAL[tipo]
    for nombre, plantilla in ciudad.get("portales", {}).items():
        base = plantilla.format(tipo_i24=i24, tipo_viv=viv)
        for p in range(1, paginas + 1):
            if p == 1:
                out.append(base)
            elif nombre == "inmuebles24":
                out.append(base.replace(".html", f"-pagina-{p}.html"))
            elif nombre == "vivanuncios":
                out.append(re.sub(r"p1$", f"p{p}", base))
    return out


def cambios_de_precio(existentes: dict[str, dict], nuevos: list[dict], ahora: datetime) -> list[dict]:
    """Por cada anuncio ya conocido cuyo precio cambió, una fila de historial."""
    cambios = []
    for a in nuevos:
        e = existentes.get(a["url"])
        if e and e.get("id") and abs(float(e["precio"]) - float(a["precio"])) >= 1:
            cambios.append({"listing_id": e["id"], "fecha": ahora.isoformat(), "precio": a["precio"]})
    return cambios


def por_dar_de_baja(vivos: list[dict], ahora: datetime, dias: int = DIAS_BAJA) -> list[int]:
    limite = ahora - timedelta(days=dias)
    out = []
    for f in vivos:
        visto = pd.Timestamp(f["ultimo_visto"])
        visto = visto.tz_localize("UTC") if visto.tzinfo is None else visto
        if f.get("fecha_baja") is None and visto < limite:
            out.append(int(f["id"]))
    return out


async def _geocodificar_lote(anuncios: list[dict], ciudad: str, estado: str) -> None:
    from ..service import UbicacionAmplia, geocodificar
    cache: dict[str, tuple | None] = {}
    for a in anuncios:
        if a.get("lat") is not None:
            continue
        texto = f"{a.get('ubicacion') or ''}, {ciudad}, {estado}, México".strip(", ")
        if texto not in cache:
            try:
                cache[texto] = await geocodificar(texto)
            except UbicacionAmplia:
                cache[texto] = None      # solo la ciudad: no sirve como ubicación

        g = cache[texto]
        if g:
            a["lat"], a["lon"] = g[0], g[1]
            # Un anuncio de portal casi nunca trae número exterior: si Google
            # no lo ubica a nivel azotea es centro de calle o colonia.
            a["precision_ubicacion"] = g[2]
        a["colonia"] = (a.get("ubicacion") or "").split(",")[0][:120] or None


def _a_fila(a: dict, ciudad: dict, ahora: datetime) -> dict:
    fila = {k: a.get(k) for k in ("url", "fuente", "tipo", "operacion", "precio", "moneda", "m2_construidos",
                                   "m2_terreno", "recamaras", "banos", "estacionamientos", "lat", "lon",
                                   "precision_ubicacion", "colonia")}
    fila.update({"estado": ciudad["estado"], "municipio": ciudad["nombre"], "ultimo_visto": ahora.isoformat(),
                 "descripcion": a.get("titulo")})
    if fila.get("lat") is not None:
        for r in (7, 8, 9):
            fila[f"h3_{r}"] = geo.celda(fila["lat"], fila["lon"], r)
    for k in ("recamaras", "banos", "estacionamientos"):
        if fila.get(k) is not None:
            fila[k] = int(round(fila[k]))
    return fila


async def recolectar_ciudad(ciudad: dict) -> list[dict]:
    from routers.avm_websearch import _avm_cache_lookup, _avm_cache_store, _firecrawl_scrape
    anuncios = []
    for tipo in TIPO_PORTAL:
        for url in urls_portal(ciudad, tipo):
            texto = await _avm_cache_lookup(url)
            if texto is None:
                r = await _firecrawl_scrape(url)
                if not r.get("ok"):
                    continue
                texto = r["page_text"]
                await _avm_cache_store(url, "", ciudad["nombre"], texto)
            anuncios += parsear_bloque(texto, tipo)
    return anuncios


async def desde_cache() -> list[tuple[dict, str]]:
    """Anuncios que ya están en avm_scrape_cache (valuaciones pasadas)."""
    from .repo import leer_todo
    filas = await leer_todo("avm_scrape_cache", {"select": "url,ciudad,page_text"}, orden="url")
    out = []
    for f in filas:
        for a in parsear_bloque(f.get("page_text") or ""):
            out.append((a, f.get("ciudad") or ""))
    return out


async def correr() -> dict:
    from . import clean, dedupe
    from .repo import leer_todo, listings_a_df, marcar, registrar_precios, registros, upsert_listings
    ahora = datetime.now(timezone.utc)
    ciudades = {c["nombre"].lower(): c for c in S.ciudades()}
    resumen = {"leidos": 0, "nuevos_o_actualizados": 0, "cambios_precio": 0, "bajas": 0}

    lotes: dict[str, list[dict]] = {k: [] for k in ciudades}
    for a, ciudad in await desde_cache():
        if ciudad.lower() in lotes:
            lotes[ciudad.lower()].append(a)
    for k, c in ciudades.items():
        try:
            lotes[k] += await recolectar_ciudad(c)
        except Exception as exc:
            log.warning("Ingesta %s falló: %s", c["nombre"], exc)

    existentes = {f["url"]: f for f in await leer_todo("avm_listings", {"select": "id,url,precio,fecha_baja,ultimo_visto"})}
    for k, anuncios in lotes.items():
        unicos = list({a["url"]: a for a in anuncios}.values())
        resumen["leidos"] += len(unicos)
        await _geocodificar_lote(unicos, ciudades[k]["nombre"], ciudades[k]["estado"])
        filas = [_a_fila(a, ciudades[k], ahora) for a in unicos]
        for f in filas:
            if f["url"] not in existentes:
                f["fecha_alta"] = date.today().isoformat()
            else:
                f["fecha_baja"] = None      # reapareció
        await registrar_precios(cambios_de_precio(existentes, filas, ahora))
        resumen["cambios_precio"] += len(cambios_de_precio(existentes, filas, ahora))
        guardados = await upsert_listings(filas)
        resumen["nuevos_o_actualizados"] += len(guardados)

    vivos = await leer_todo("avm_listings", {"select": "id,ultimo_visto,fecha_baja", "fecha_baja": "is.null"})
    bajas = por_dar_de_baja(vivos, ahora)
    if bajas:
        await marcar(bajas, {"fecha_baja": date.today().isoformat()})
    resumen["bajas"] = len(bajas)

    # Limpieza + duplicados sobre todo lo que sigue vivo.
    df = listings_a_df(await leer_todo("avm_listings", {"fecha_baja": "is.null"}))
    if not df.empty:
        limpio = clean.limpiar(df, S.ciudades())
        agrupado = dedupe.agrupar(limpio[limpio["calidad"] == "ok"])
        limpio = limpio.merge(agrupado[["id", "cluster_id", "es_principal"]], on="id", how="left", suffixes=("_v", ""))
        limpio["es_principal"] = limpio["es_principal"].fillna(False)
        filas = registros(limpio, ["id", "url", "fuente", "tipo", "operacion", "precio", "calidad", "motivo_descarte",
                                   "cluster_id", "es_principal", "precision_ubicacion"])
        await upsert_listings(filas)
        resumen["limpieza"] = clean.resumen(limpio)
    return resumen


if __name__ == "__main__":
    print(asyncio.run(correr()))
