from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import httpx
import os
import time
import re
import json
from typing import Optional
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
    return {"status": "Brokr API activa", "version": "2.0"}

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
# AVM — HELPERS
# ────────────────────────────────────────────
class AVMRequest(BaseModel):
    colonia: str
    ciudad: str
    tipo: str                              # casa, departamento, terreno, local, comercial
    operacion: str                         # venta, renta
    m2_construccion: Optional[float] = None
    m2_terreno:      Optional[float] = None
    recamaras:       Optional[int]   = None
    banos:           Optional[float] = None
    estado:          Optional[str]   = "bueno"   # malo, regular, bueno, excelente
    anio_construccion: Optional[int] = None

def slugify(text: str) -> str:
    text = text.lower().strip()
    for a, b in [('á','a'),('é','e'),('í','i'),('ó','o'),('ú','u'),('ü','u'),('ñ','n')]:
        text = text.replace(a, b)
    text = re.sub(r'[^a-z0-9\s-]', '', text)
    text = re.sub(r'\s+', '-', text)
    return re.sub(r'-+', '-', text).strip('-')

def parse_price(text: str) -> Optional[float]:
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

# ────────────────────────────────────────────
# SCRAPER — Inmuebles24
# ────────────────────────────────────────────
async def scrape_inmuebles24(colonia: str, ciudad: str,
                              tipo: str, operacion: str) -> list:
    cache_key = f"i24_{slugify(colonia)}_{slugify(ciudad)}_{tipo}_{operacion}"
    cached = cache_get(cache_key)
    if cached is not None:
        return cached

    tipo_map = {
        "casa": "casas", "departamento": "departamentos",
        "terreno": "terrenos", "local": "locales-comerciales",
        "comercial": "locales-comerciales", "oficina": "oficinas",
        "bodega": "bodegas",
    }
    op_map = {"venta": "venta", "renta": "renta"}
    tipo_url = tipo_map.get(tipo.lower(), "casas")
    op_url   = op_map.get(operacion.lower(), "venta")
    loc      = f"{slugify(colonia)}-{slugify(ciudad)}"

    urls = [
        f"https://www.inmuebles24.com/{tipo_url}-en-{op_url}/{loc}/",
        f"https://www.inmuebles24.com/{tipo_url}-en-{op_url}-en-{loc}/",
        f"https://www.inmuebles24.com/{tipo_url}-en-{op_url}/{slugify(ciudad)}/",
    ]

    headers = {
        "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/121.0.0.0 Safari/537.36"),
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.8",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    html = None
    async with httpx.AsyncClient(timeout=25, follow_redirects=True) as client:
        for url in urls:
            try:
                r = await client.get(url, headers=headers)
                if r.status_code == 200 and len(r.text) > 5000:
                    html = r.text
                    break
            except:
                continue

    if not html:
        return []

    soup = BeautifulSoup(html, 'html.parser')
    comparables = []
    seen_prices = set()

    # ── Strategy 1: JSON-LD structured data ──
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
                if price and price not in seen_prices:
                    seen_prices.add(price)
                    comparables.append({
                        'precio': price,
                        'titulo': item.get('name', f'{tipo} en {colonia}')[:80],
                        'm2_construccion': None,
                        'm2_terreno': None,
                        'recamaras': None,
                        'banos': None,
                        'url': item.get('url', ''),
                        'fuente': 'Inmuebles24',
                    })
        except:
            continue

    # ── Strategy 2: Listing cards ──
    card_selectors = [
        'div[data-posting-type]', 'div.listing-card',
        'article.posting-card', '[class*="postingCard"]',
        '[class*="listing-item"]', 'div[class*="posting"]',
        'li[class*="posting"]',
    ]
    cards = []
    for sel in card_selectors:
        cards = soup.select(sel)
        if len(cards) >= 2:
            break

    for card in cards[:25]:
        try:
            # Price
            price_el = (card.select_one('[class*="price"]') or
                        card.select_one('[data-price]') or
                        card.select_one('span[class*="Price"]'))
            price_text = (card.get('data-price') or
                          card.get('data-posting-price') or
                          (price_el.get_text(strip=True) if price_el else ''))
            price = parse_price(price_text)
            if not price or price in seen_prices:
                continue
            seen_prices.add(price)

            # Title
            title_el = card.select_one('h2, h3, [class*="title"], [class*="Title"]')
            title = (title_el.get_text(strip=True) if title_el
                     else f'{tipo.capitalize()} en {colonia}')

            # Attributes from full card text
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
            url  = href if href.startswith('http') else f"https://www.inmuebles24.com{href}"

            comparables.append({
                'precio': price, 'titulo': title[:80],
                'm2_construccion': m2c, 'm2_terreno': m2t,
                'recamaras': rec, 'banos': ban,
                'url': url, 'fuente': 'Inmuebles24',
            })
        except:
            continue

    # ── Strategy 3: Regex fallback on raw HTML ──
    if len(comparables) < 3:
        for p_str in re.findall(r'"price"\s*:\s*"?(\d{5,9})"?', html)[:20]:
            try:
                p = float(p_str)
                if p not in seen_prices and 100_000 <= p <= 99_000_000:
                    seen_prices.add(p)
                    comparables.append({
                        'precio': p,
                        'titulo': f'{tipo.capitalize()} en {colonia}',
                        'm2_construccion': None, 'm2_terreno': None,
                        'recamaras': None, 'banos': None,
                        'url': '', 'fuente': 'Inmuebles24',
                    })
            except:
                continue

    # ── Filter outliers ──
    if len(comparables) >= 3:
        prices = sorted(c['precio'] for c in comparables)
        median = prices[len(prices) // 2]
        comparables = [c for c in comparables
                       if median * 0.25 <= c['precio'] <= median * 4.0]

    result = comparables[:15]
    cache_set(cache_key, result)
    return result

# ────────────────────────────────────────────
# HEDONIC MODEL
# ────────────────────────────────────────────
def ajuste_hedonico(comp: dict, sujeto: dict) -> dict:
    precio_base = comp['precio']
    ajustes = []
    factor  = 1.0

    # m² adjustment (sqrt scaling — larger units are cheaper per m²)
    m2s = sujeto.get('m2_construccion')
    m2c = comp.get('m2_construccion')
    if m2s and m2c and m2c > 0 and abs(m2s - m2c) > 5:
        ratio = (m2s / m2c) ** 0.5
        factor *= ratio
        ajustes.append(f"m² construcción ({'+' if m2s>m2c else ''}{m2s-m2c:.0f} m²): "
                       f"{'+' if ratio>1 else ''}{(ratio-1)*100:.1f}%")

    # Bedrooms (4% per room difference)
    rs = sujeto.get('recamaras')
    rc = comp.get('recamaras')
    if rs and rc and rs != rc:
        diff  = rs - rc
        adj   = 1 + diff * 0.04
        factor *= adj
        ajustes.append(f"recámaras ({'+' if diff>0 else ''}{diff}): "
                       f"{'+' if diff>0 else ''}{diff*4}%")

    # Conservation state
    estado_adj = {"malo": -0.15, "regular": -0.07, "bueno": 0.0, "excelente": 0.08}
    adj_estado = estado_adj.get(sujeto.get('estado', 'bueno'), 0.0)
    if adj_estado != 0:
        factor *= (1 + adj_estado)
        ajustes.append(f"estado ({sujeto.get('estado')}): "
                       f"{'+' if adj_estado>0 else ''}{adj_estado*100:.0f}%")

    # Age adjustment
    anio = sujeto.get('anio_construccion')
    if anio:
        anos = datetime.now().year - anio
        decades = (anos - 10) / 10
        age_adj = max(-0.20, min(0.15, -0.015 * decades))
        if abs(age_adj) > 0.01:
            factor *= (1 + age_adj)
            ajustes.append(f"antigüedad ({anos} años): "
                           f"{'+' if age_adj>0 else ''}{age_adj*100:.1f}%")

    # Offer-to-close discount (8%)
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
    comparables_raw = await scrape_inmuebles24(
        req.colonia, req.ciudad, req.tipo, req.operacion
    )

    if len(comparables_raw) < 2:
        raise HTTPException(
            status_code=422,
            detail=(f"No se encontraron comparables suficientes en "
                    f"{req.colonia}, {req.ciudad}. "
                    f"Intenta con una colonia más amplia o la ciudad completa.")
        )

    sujeto = {
        'm2_construccion':  req.m2_construccion,
        'm2_terreno':       req.m2_terreno,
        'recamaras':        req.recamaras,
        'banos':            req.banos,
        'estado':           req.estado,
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
    p_trim  = precios[trim: n - trim] if n > 4 else precios

    valor_minimo   = round(min(p_trim), -3)
    valor_probable = round(sum(p_trim) / len(p_trim), -3)
    valor_maximo   = round(max(p_trim), -3)

    pm2_list = []
    for c in ajustados:
        m2 = c.get('m2_construccion') or req.m2_construccion
        if m2 and m2 > 0:
            pm2_list.append(c['precio_ajustado'] / m2)
    pm2_prom = round(sum(pm2_list) / len(pm2_list)) if pm2_list else None

    return {
        "colonia":            req.colonia,
        "ciudad":             req.ciudad,
        "tipo":               req.tipo,
        "operacion":          req.operacion,
        "num_comparables":    len(ajustados),
        "valor_minimo":       valor_minimo,
        "valor_probable":     valor_probable,
        "valor_maximo":       valor_maximo,
        "precio_m2_promedio": pm2_prom,
        "comparables":        ajustados[:10],
        "nota": ("Valores estimados con base en oferta publicada en Inmuebles24, "
                 "con ajustes hedónicos y descuento oferta→cierre del 8%. "
                 "El valor definitivo requiere inspección física y avalúo formal."),
        "timestamp": time.strftime("%Y-%m-%d %H:%M"),
    }
