from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os
import time
import re
import json
import asyncio
from typing import Optional, List
from datetime import datetime
from bs4 import BeautifulSoup

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

EB_API_KEY = os.environ.get("EB_API_KEY", "")
EB_BASE    = "https://api.easybroker.com/v1"

# ── CACHE EN MEMORIA (TTL 24h) ──
_cache: dict = {}
CACHE_TTL = 86400

def cache_get(key):
    if key in _cache:
        data, ts = _cache[key]
        if time.time() - ts < CACHE_TTL:
            return data
        del _cache[key]
    return None

def cache_set(key, data):
    _cache[key] = (data, time.time())

# ────────────────────────────────────────────
# EASYBROKER ENDPOINTS
# ────────────────────────────────────────────
@app.get("/")
def root():
    return {"status": "Brokr API activa", "version": "3.0"}

@app.get("/propiedad/{property_id}")
async def get_propiedad(property_id: str):
    if not EB_API_KEY:
        raise HTTPException(status_code=500, detail="EB_API_KEY no configurada")
    headers = {"X-Authorization": EB_API_KEY, "accept": "application/json"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{EB_BASE}/properties/{property_id}", headers=headers)
        if r.status_code == 404:
            raise HTTPException(status_code=404, detail="Propiedad no encontrada")
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail="Error EasyBroker")
        return r.json()

@app.get("/propiedades")
async def get_propiedades(page: int = 1, limit: int = 20):
    if not EB_API_KEY:
        raise HTTPException(status_code=500, detail="EB_API_KEY no configurada")
    headers = {"X-Authorization": EB_API_KEY, "accept": "application/json"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(f"{EB_BASE}/properties", headers=headers,
                             params={"page": page, "limit": limit})
        if r.status_code != 200:
            raise HTTPException(status_code=r.status_code, detail="Error EasyBroker")
        return r.json()

# ────────────────────────────────────────────
# HELPERS
# ────────────────────────────────────────────
class AVMRequest(BaseModel):
    colonia: str
    ciudad: str
    tipo: str
    operacion: str
    m2_construccion: Optional[float] = None
    m2_terreno:      Optional[float] = None
    recamaras:       Optional[int]   = None
    banos:           Optional[float] = None
    estado:          Optional[str]   = "bueno"
    anio_construccion: Optional[int] = None

def slugify(text: str) -> str:
    text = text.lower().strip()
    for a, b in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ü','u'),('ñ','n')]:
        text = text.replace(a, b)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text)
    return re.sub(r'-+', '-', text).strip('-')

def parse_price(text) -> Optional[float]:
    if not text:
        return None
    t = str(text).upper().replace(',', '').strip()
    m = re.search(r'(\d+\.?\d*)\s*M(?:DP|DPS|ILLONES?)?', t)
    if m:
        return float(m.group(1)) * 1_000_000
    n = re.sub(r'[^\d.]', '', t)
    try:
        v = float(n)
        if 50_000 <= v <= 999_000_000:
            return v
    except:
        pass
    return None

HEADERS_BROWSER = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/121.0.0.0 Safari/537.36"),
    "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

def extract_from_html(html: str, colonia: str, tipo: str, fuente: str) -> list:
    """Generic extractor — works on any portal HTML."""
    soup = BeautifulSoup(html, 'html.parser')
    comparables = []
    seen = set()

    # ── JSON-LD ──
    for script in soup.find_all('script', type='application/ld+json'):
        try:
            data = json.loads(script.string or '{}')
            items = data if isinstance(data, list) else [data]
            for item in items:
                if not isinstance(item, dict):
                    continue
                price_raw = (item.get('price') or
                             (item.get('offers') or {}).get('price') or '')
                price = parse_price(str(price_raw))
                if price and price not in seen:
                    seen.add(price)
                    comparables.append({
                        'precio': price,
                        'titulo': str(item.get('name', f'{tipo} en {colonia}'))[:80],
                        'm2_construccion': None, 'm2_terreno': None,
                        'recamaras': None, 'banos': None,
                        'url': str(item.get('url', '')),
                        'fuente': fuente,
                    })
        except:
            continue

    # ── Listing cards ──
    card_selectors = [
        'div[data-posting-type]', 'div.listing-card', 'article.posting-card',
        '[class*="postingCard"]', '[class*="listing-item"]',
        'div[class*="posting"]', 'li[class*="posting"]',
        '[class*="PropertyCard"]', '[class*="property-card"]',
        'article[class*="card"]',
    ]
    cards = []
    for sel in card_selectors:
        cards = soup.select(sel)
        if len(cards) >= 2:
            break

    for card in cards[:30]:
        try:
            price_el = (card.select_one('[class*="price"]') or
                        card.select_one('[data-price]') or
                        card.select_one('span[class*="Price"]'))
            price_text = (card.get('data-price') or
                          card.get('data-posting-price') or
                          (price_el.get_text(strip=True) if price_el else ''))
            price = parse_price(price_text)
            if not price or price in seen:
                continue
            seen.add(price)

            title_el = card.select_one('h2,h3,[class*="title"],[class*="Title"]')
            title = (title_el.get_text(strip=True) if title_el
                     else f'{tipo.capitalize()} en {colonia}')

            attrs = card.get_text(' ', strip=True)
            m2c = m2t = rec = ban = None
            m2c_m = re.search(r'(\d+)\s*m[²2]\s*(?:cub|cons|total)', attrs, re.I)
            m2t_m = re.search(r'(\d+)\s*m[²2]\s*(?:terr|lote)', attrs, re.I)
            rec_m = re.search(r'(\d+)\s*(?:rec[aá]m|hab|cuart)', attrs, re.I)
            ban_m = re.search(r'(\d+\.?\d*)\s*ba[ñn]', attrs, re.I)
            m2g_m = re.search(r'(\d+)\s*m[²2]', attrs)
            if m2c_m: m2c = float(m2c_m.group(1))
            if m2t_m: m2t = float(m2t_m.group(1))
            if rec_m:  rec = int(rec_m.group(1))
            if ban_m:  ban = float(ban_m.group(1))
            if not m2c and m2g_m: m2c = float(m2g_m.group(1))

            link = card.select_one('a[href]')
            href = link.get('href', '') if link else ''
            base = f"https://www.{fuente.lower().replace(' ','')}.com.mx"
            url  = href if href.startswith('http') else f"{base}{href}"

            comparables.append({
                'precio': price, 'titulo': title[:80],
                'm2_construccion': m2c, 'm2_terreno': m2t,
                'recamaras': rec, 'banos': ban,
                'url': url, 'fuente': fuente,
            })
        except:
            continue

    # ── Regex fallback ──
    if len(comparables) < 3:
        for p_str in re.findall(r'"price"\s*:\s*"?(\d{5,9})"?', html)[:20]:
            try:
                p = float(p_str)
                if p not in seen and 100_000 <= p <= 99_000_000:
                    seen.add(p)
                    comparables.append({
                        'precio': p, 'titulo': f'{tipo.capitalize()} en {colonia}',
                        'm2_construccion': None, 'm2_terreno': None,
                        'recamaras': None, 'banos': None,
                        'url': '', 'fuente': fuente,
                    })
            except:
                continue

    return comparables

# ────────────────────────────────────────────
# SCRAPERS — one per portal
# ────────────────────────────────────────────
async def scrape_inmuebles24(loc: str, tipo: str, operacion: str,
                              colonia: str) -> list:
    tipo_map = {
        "casa":"casas","departamento":"departamentos","terreno":"terrenos",
        "local":"locales-comerciales","comercial":"locales-comerciales",
        "oficina":"oficinas","bodega":"bodegas",
    }
    op_map = {"venta":"venta","renta":"renta"}
    t = tipo_map.get(tipo.lower(), "casas")
    o = op_map.get(operacion.lower(), "venta")
    urls = [
        f"https://www.inmuebles24.com/{t}-en-{o}/{loc}/",
        f"https://www.inmuebles24.com/{t}-en-{o}-en-{loc}/",
    ]
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for url in urls:
            try:
                r = await client.get(url, headers=HEADERS_BROWSER)
                if r.status_code == 200 and len(r.text) > 5000:
                    return extract_from_html(r.text, colonia, tipo, "Inmuebles24")
            except:
                continue
    return []

async def scrape_lamudi(loc: str, tipo: str, operacion: str,
                         colonia: str) -> list:
    tipo_map = {
        "casa":"casas","departamento":"apartamentos","terreno":"terrenos",
        "local":"locales-comerciales","comercial":"locales-comerciales",
        "oficina":"oficinas","bodega":"bodegas",
    }
    op_map = {"venta":"venta","renta":"renta"}
    t = tipo_map.get(tipo.lower(), "casas")
    o = op_map.get(operacion.lower(), "venta")
    urls = [
        f"https://www.lamudi.com.mx/{loc}/{t}/for-{o}/",
        f"https://www.lamudi.com.mx/mexico/{t}/for-{o}/?q={loc}",
    ]
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for url in urls:
            try:
                r = await client.get(url, headers=HEADERS_BROWSER)
                if r.status_code == 200 and len(r.text) > 5000:
                    return extract_from_html(r.text, colonia, tipo, "Lamudi")
            except:
                continue
    return []

async def scrape_vivanuncios(loc: str, tipo: str, operacion: str,
                              colonia: str) -> list:
    tipo_map = {
        "casa":"casas","departamento":"departamentos","terreno":"terrenos",
        "local":"locales-comerciales","comercial":"locales-comerciales",
        "oficina":"oficinas",
    }
    op_map = {"venta":"venta","renta":"renta"}
    t = tipo_map.get(tipo.lower(), "casas")
    o = op_map.get(operacion.lower(), "venta")
    urls = [
        f"https://www.vivanuncios.com.mx/s-{t}-en-{o}/{loc}/v1c1101l{loc}A1/",
        f"https://www.vivanuncios.com.mx/s-{t}/{loc}/v1c1101l{loc}A1/",
    ]
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for url in urls:
            try:
                r = await client.get(url, headers=HEADERS_BROWSER)
                if r.status_code == 200 and len(r.text) > 5000:
                    return extract_from_html(r.text, colonia, tipo, "Vivanuncios")
            except:
                continue
    return []

async def scrape_propiedades(loc: str, tipo: str, operacion: str,
                              colonia: str) -> list:
    tipo_map = {
        "casa":"casas","departamento":"departamentos","terreno":"terrenos",
        "local":"locales","comercial":"locales","oficina":"oficinas",
    }
    op_map = {"venta":"venta","renta":"renta"}
    t = tipo_map.get(tipo.lower(), "casas")
    o = op_map.get(operacion.lower(), "venta")
    urls = [
        f"https://propiedades.com/{loc}/{t}-en-{o}",
        f"https://propiedades.com/michoacan/{t}-en-{o}?q={loc}",
    ]
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        for url in urls:
            try:
                r = await client.get(url, headers=HEADERS_BROWSER)
                if r.status_code == 200 and len(r.text) > 5000:
                    return extract_from_html(r.text, colonia, tipo, "Propiedades.com")
            except:
                continue
    return []

async def scrape_easybroker_api(colonia: str, ciudad: str,
                                 tipo: str, operacion: str) -> list:
    """Use EasyBroker API directly — most reliable source."""
    if not EB_API_KEY:
        return []
    tipo_map = {
        "casa":"Casas","departamento":"Departamentos","terreno":"Terrenos",
        "local":"Locales comerciales","comercial":"Locales comerciales",
        "oficina":"Oficinas","bodega":"Bodegas",
    }
    op_map = {"venta":"Venta","renta":"Renta"}

    headers = {"X-Authorization": EB_API_KEY, "accept": "application/json"}
    params = {
        "search[city]": ciudad,
        "search[property_type]": tipo_map.get(tipo.lower(), "Casas"),
        "search[operation_type]": op_map.get(operacion.lower(), "Venta"),
        "limit": 50,
    }
    comparables = []
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(f"{EB_BASE}/properties",
                                 headers=headers, params=params)
            if r.status_code != 200:
                return []
            data = r.json()
            props = data.get('content', [])

            for p in props:
                # Filter by colonia if present in address
                address = (p.get('address','') + ' ' +
                           (p.get('location',{}).get('name',''))).lower()
                colonia_sl = colonia.lower()
                # Include if colonia matches OR if no location filter possible
                op = p.get('operations', [{}])[0] if p.get('operations') else {}
                price = parse_price(str(op.get('amount', 0)))
                if not price:
                    continue

                comparables.append({
                    'precio': price,
                    'titulo': p.get('title', f'{tipo} en {colonia}')[:80],
                    'm2_construccion': p.get('construction_size'),
                    'm2_terreno':      p.get('lot_size'),
                    'recamaras':       p.get('bedrooms'),
                    'banos':           p.get('bathrooms'),
                    'url': f"https://www.easybroker.com/properties/{p.get('public_id','')}",
                    'fuente': 'EasyBroker',
                    'colonia_match': colonia_sl in address,
                })
    except:
        pass
    return comparables

def remove_outliers(comparables: list) -> list:
    if len(comparables) < 3:
        return comparables
    prices = sorted(c['precio'] for c in comparables)
    median = prices[len(prices)//2]
    return [c for c in comparables
            if median * 0.25 <= c['precio'] <= median * 4.0]

def filter_by_pm2(comparables: list, m2: float, tolerance: float = 0.35) -> list:
    """Keep only comparables within ±tolerance of median price/m²."""
    with_m2 = [(c, c['precio']/m2) for c in comparables
               if c.get('m2_construccion') and c['m2_construccion'] > 0]
    if len(with_m2) < 3:
        return comparables
    pm2s = sorted(pm2 for _, pm2 in with_m2)
    median_pm2 = pm2s[len(pm2s)//2]
    keep = {id(c) for c, pm2 in with_m2
            if median_pm2*(1-tolerance) <= pm2 <= median_pm2*(1+tolerance)}
    # Always keep those without m2 data
    return [c for c in comparables
            if id(c) in keep or not c.get('m2_construccion')]

# ────────────────────────────────────────────
# MULTI-LEVEL SCRAPER
# ────────────────────────────────────────────
async def get_comparables(colonia: str, ciudad: str,
                           tipo: str, operacion: str,
                           m2_construccion: Optional[float] = None) -> tuple:
    """
    Returns (comparables, nivel, fuentes_usadas)
    Nivel 1 = colonia exacta, Nivel 2 = ciudad filtrada, Nivel 3 = ciudad amplia
    """
    MIN_COMPARABLES = 5

    loc_colonia = f"{slugify(colonia)}-{slugify(ciudad)}"
    loc_ciudad  = slugify(ciudad)

    # ── NIVEL 1: Colonia exacta — todos los portales en paralelo ──
    cache_key_1 = f"nivel1_{loc_colonia}_{tipo}_{operacion}"
    nivel1 = cache_get(cache_key_1)

    if nivel1 is None:
        tasks = [
            scrape_inmuebles24(loc_colonia, tipo, operacion, colonia),
            scrape_lamudi(loc_colonia, tipo, operacion, colonia),
            scrape_vivanuncios(loc_colonia, tipo, operacion, colonia),
            scrape_propiedades(loc_colonia, tipo, operacion, colonia),
            scrape_easybroker_api(colonia, ciudad, tipo, operacion),
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        nivel1 = []
        for r in results:
            if isinstance(r, list):
                nivel1.extend(r)
        nivel1 = remove_outliers(nivel1)
        cache_set(cache_key_1, nivel1)

    # Deduplicate by price proximity
    nivel1_dedup = []
    seen_prices = set()
    for c in nivel1:
        rounded = round(c['precio'], -4)
        if rounded not in seen_prices:
            seen_prices.add(rounded)
            nivel1_dedup.append(c)

    fuentes = list(set(c['fuente'] for c in nivel1_dedup))

    if len(nivel1_dedup) >= MIN_COMPARABLES:
        return nivel1_dedup[:15], 1, fuentes

    # ── NIVEL 2: Ciudad completa con filtro de precio/m² ──
    cache_key_2 = f"nivel2_{loc_ciudad}_{tipo}_{operacion}"
    nivel2_raw = cache_get(cache_key_2)

    if nivel2_raw is None:
        tasks2 = [
            scrape_inmuebles24(loc_ciudad, tipo, operacion, ciudad),
            scrape_lamudi(loc_ciudad, tipo, operacion, ciudad),
            scrape_vivanuncios(loc_ciudad, tipo, operacion, ciudad),
            scrape_propiedades(loc_ciudad, tipo, operacion, ciudad),
            scrape_easybroker_api(colonia, ciudad, tipo, operacion),
        ]
        results2 = await asyncio.gather(*tasks2, return_exceptions=True)
        nivel2_raw = []
        for r in results2:
            if isinstance(r, list):
                nivel2_raw.extend(r)
        nivel2_raw = remove_outliers(nivel2_raw)
        cache_set(cache_key_2, nivel2_raw)

    # Merge nivel1 + nivel2 and deduplicate
    merged = nivel1_dedup[:]
    seen2 = set(round(c['precio'],-4) for c in merged)
    for c in nivel2_raw:
        r = round(c['precio'],-4)
        if r not in seen2:
            seen2.add(r)
            merged.append(c)

    # Apply price/m² filter to avoid mixing zones
    if m2_construccion and m2_construccion > 0 and len(merged) >= 5:
        filtered = filter_by_pm2(merged, m2_construccion, tolerance=0.35)
        if len(filtered) >= MIN_COMPARABLES:
            fuentes2 = list(set(c['fuente'] for c in filtered))
            return filtered[:15], 2, fuentes2

    if len(merged) >= MIN_COMPARABLES:
        fuentes2 = list(set(c['fuente'] for c in merged))
        return merged[:15], 2, fuentes2

    # ── NIVEL 3: Ciudad amplia sin filtro adicional ──
    if len(merged) >= 2:
        fuentes3 = list(set(c['fuente'] for c in merged))
        return merged[:15], 3, fuentes3

    return [], 3, []

# ────────────────────────────────────────────
# HEDONIC MODEL
# ────────────────────────────────────────────
def ajuste_hedonico(comp: dict, sujeto: dict) -> dict:
    precio_base = comp['precio']
    ajustes = []
    factor  = 1.0

    # m² construction (sqrt scaling)
    m2s = sujeto.get('m2_construccion')
    m2c = comp.get('m2_construccion')
    if m2s and m2c and m2c > 0 and abs(m2s - m2c) > 5:
        ratio = (m2s / m2c) ** 0.5
        factor *= ratio
        diff = m2s - m2c
        ajustes.append(f"m² ({'+' if diff>0 else ''}{diff:.0f}): "
                       f"{'+' if ratio>1 else ''}{(ratio-1)*100:.1f}%")

    # Bedrooms (4% per room)
    rs = sujeto.get('recamaras')
    rc = comp.get('recamaras')
    if rs and rc and rs != rc:
        diff  = rs - rc
        factor *= (1 + diff * 0.04)
        ajustes.append(f"recámaras ({'+' if diff>0 else ''}{diff}): "
                       f"{'+' if diff>0 else ''}{diff*4}%")

    # Conservation state
    estado_adj = {"malo":-0.15,"regular":-0.07,"bueno":0.0,"excelente":0.08}
    adj_e = estado_adj.get(sujeto.get('estado','bueno'), 0.0)
    if adj_e != 0:
        factor *= (1 + adj_e)
        ajustes.append(f"estado ({sujeto.get('estado')}): "
                       f"{'+' if adj_e>0 else ''}{adj_e*100:.0f}%")

    # Age
    anio = sujeto.get('anio_construccion')
    if anio:
        anos = datetime.now().year - anio
        age_adj = max(-0.20, min(0.15, -0.015 * ((anos - 10) / 10)))
        if abs(age_adj) > 0.01:
            factor *= (1 + age_adj)
            ajustes.append(f"antigüedad ({anos} años): "
                           f"{'+' if age_adj>0 else ''}{age_adj*100:.1f}%")

    # Offer-to-close discount 8%
    factor *= 0.92
    ajustes.append("desc. oferta→cierre: -8%")

    return {
        **comp,
        'precio_ajustado': round(precio_base * factor, -3),
        'factor_total':    round(factor, 4),
        'ajustes':         ajustes,
    }

# ────────────────────────────────────────────
# AVM ENDPOINT
# ────────────────────────────────────────────
@app.post("/avm")
async def calcular_avm(req: AVMRequest):

    comparables_raw, nivel, fuentes = await get_comparables(
        req.colonia, req.ciudad, req.tipo, req.operacion,
        req.m2_construccion
    )

    if len(comparables_raw) < 2:
        raise HTTPException(
            status_code=422,
            detail=(f"No se encontraron comparables en {req.colonia} ni en "
                    f"{req.ciudad}. Verifica que la colonia y ciudad existan "
                    f"en los portales inmobiliarios.")
        )

    sujeto = {
        'm2_construccion':   req.m2_construccion,
        'm2_terreno':        req.m2_terreno,
        'recamaras':         req.recamaras,
        'banos':             req.banos,
        'estado':            req.estado,
        'anio_construccion': req.anio_construccion,
    }

    ajustados = []
    for comp in comparables_raw:
        try:
            ajustados.append(ajuste_hedonico(comp, sujeto))
        except:
            continue

    if not ajustados:
        raise HTTPException(status_code=422, detail="Error procesando comparables")

    precios = sorted(c['precio_ajustado'] for c in ajustados)
    n       = len(precios)
    trim    = max(1, n // 10)
    p_trim  = precios[trim: n-trim] if n > 4 else precios

    valor_minimo   = round(min(p_trim), -3)
    valor_probable = round(sum(p_trim) / len(p_trim), -3)
    valor_maximo   = round(max(p_trim), -3)

    pm2_list = []
    for c in ajustados:
        m2 = c.get('m2_construccion') or req.m2_construccion
        if m2 and m2 > 0:
            pm2_list.append(c['precio_ajustado'] / m2)
    pm2_prom = round(sum(pm2_list) / len(pm2_list)) if pm2_list else None

    # Nivel-based confidence message
    nivel_msg = {
        1: f"Alta confianza — {len(ajustados)} comparables encontrados en {req.colonia}.",
        2: f"Confianza media — pocos comparables en {req.colonia}, se amplió a {req.ciudad} con filtro de precio/m².",
        3: f"Confianza baja — muestra amplia de {req.ciudad}. Se recomienda verificar con el agente.",
    }.get(nivel, "")

    return {
        "colonia":            req.colonia,
        "ciudad":             req.ciudad,
        "tipo":               req.tipo,
        "operacion":          req.operacion,
        "nivel":              nivel,
        "nivel_mensaje":      nivel_msg,
        "fuentes":            fuentes,
        "num_comparables":    len(ajustados),
        "valor_minimo":       valor_minimo,
        "valor_probable":     valor_probable,
        "valor_maximo":       valor_maximo,
        "precio_m2_promedio": pm2_prom,
        "comparables":        ajustados[:10],
        "nota": ("Valores estimados con base en oferta publicada en portales inmobiliarios, "
                 "con ajustes hedónicos y descuento oferta→cierre del 8%. "
                 "El valor definitivo requiere inspección física y avalúo formal."),
        "timestamp": time.strftime("%Y-%m-%d %H:%M"),
    }
