"""Controlled web-search AVM domain with SSRF-safe public page fetching."""
from __future__ import annotations

import asyncio
from datetime import datetime
import json
import re
import time
from typing import Any, Dict, List

import httpx
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from core.auth import get_user_id_from_token
from core.config import settings
from core.http import fetch_public_http_result
from core.legacy_main_config import legacy_main_settings
from core.telemetry import _track_anthropic
from limites import exigir_cupo, exigir_sesion


router = APIRouter()
ANTHROPIC_API_KEY = settings.anthropic_api_key
ANTHROPIC_BASE = settings.anthropic_base


class AvmWebSearchRequest(BaseModel):
    colonia: str
    tipo_inmueble: str
    operacion: str = "venta"
    m2_construccion: float = 0
    m2_terreno: float = 0
    recamaras: int = 0
    banos: float = 0
    estacionamientos: int = 0
    condicion_terreno: str = ""
    ciudad: str = "Morelia"
    estado: str = "Michoacán"
    comentarios: str = ""


SEARCH_TIMEOUT = legacy_main_settings.avm_search_timeout
FETCH_TIMEOUT = legacy_main_settings.avm_fetch_timeout
MAX_SEARCH_RESULTS = legacy_main_settings.avm_max_search_results
MAX_URLS_TO_FETCH = legacy_main_settings.avm_max_urls_to_fetch
MAX_TEXT_CHARS_PER_URL = legacy_main_settings.avm_max_text_chars_per_url

PORTAL_HINTS = {
    "inmuebles24.com": "Inmuebles24",
    "lamudi.com.mx": "Lamudi",
    "propiedades.com": "Propiedades.com",
    "vivanuncios.com.mx": "Vivanuncios",
    "icasas.mx": "iCasas",
    "trovit.com.mx": "Trovit",
    "easybroker.com": "EasyBroker",
    "metroscubicos.com": "Metros Cúbicos",
    "nestoria.mx": "Nestoria",
    "mercadolibre.com.mx": "Mercado Libre Inmuebles",
}

BLOCKED_FETCH_DOMAINS = {
    "google.com", "google.com.mx", "facebook.com", "instagram.com", "tiktok.com",
    "youtube.com", "maps.google.com", "googleusercontent.com"
}

FIRECRAWL_API_KEY = legacy_main_settings.firecrawl_api_key
FIRECRAWL_CONCURRENCY = legacy_main_settings.firecrawl_concurrency
FIRECRAWL_TIMEOUT = legacy_main_settings.firecrawl_timeout

PREMIUM_FETCH_DOMAINS = {
    "inmuebles24.com",
    "lamudi.com.mx",
    "lamudi.com",
    "propiedades.com",
    "metroscubicos.com",
    "mercadolibre.com.mx",
}


async def _firecrawl_scrape(url: str) -> Dict[str, Any]:
    if not FIRECRAWL_API_KEY:
        return {"ok": False, "error": "no_api_key", "page_text": "", "credits": 0}
    payload = {
        "url": url,
        "formats": ["markdown"],
        "proxy": "auto",
        "onlyMainContent": True,
        "timeout": int(FIRECRAWL_TIMEOUT * 1000),
    }
    headers = {
        "Authorization": f"Bearer {FIRECRAWL_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=FIRECRAWL_TIMEOUT + 5) as client:
            response = await client.post(
                "https://api.firecrawl.dev/v1/scrape",
                json=payload,
                headers=headers,
            )
        if response.status_code != 200:
            return {"ok": False, "error": f"http_{response.status_code}", "page_text": "", "credits": 0}
        data_all = response.json() or {}
        if not data_all.get("success"):
            return {
                "ok": False,
                "error": data_all.get("error") or "no_success",
                "page_text": "",
                "credits": 0,
            }
        data = data_all.get("data") or {}
        text = (data.get("markdown") or "")[:MAX_TEXT_CHARS_PER_URL]
        meta = data.get("metadata") or {}
        credits = int(meta.get("creditsUsed") or data_all.get("creditsUsed") or 1)
        return {"ok": True, "page_text": text, "credits": credits}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120], "page_text": "", "credits": 0}


def _today_mx() -> str:
    return datetime.now().strftime("%d/%m/%Y")


def _round_mxn(n: float, base: int = 1000) -> int:
    try:
        return int(round(float(n) / base) * base)
    except Exception:
        return 0


def _host(url: str) -> str:
    try:
        from urllib.parse import urlparse
        host = (urlparse(url).netloc or "").lower()
        return host[4:] if host.startswith("www.") else host
    except Exception:
        return ""


def _portal_name(url: str) -> str:
    host = _host(url)
    for domain, name in PORTAL_HINTS.items():
        if domain in host:
            return name
    return host or "Fuente web"


def _canonical_url(url: str) -> str:
    try:
        from urllib.parse import urlsplit, urlunsplit
        parts = urlsplit(url)
        return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path.rstrip("/"), "", ""))
    except Exception:
        return url


def _sameish_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip()


def _build_search_queries(req: AvmWebSearchRequest) -> List[str]:
    tipo = {
        "terreno": "terreno", "casa": "casa", "departamento": "departamento",
        "local": "local comercial", "oficina": "oficina", "bodega": "bodega"
    }.get(req.tipo_inmueble, req.tipo_inmueble)
    op = "venta" if req.operacion == "venta" else "renta"
    base = f'{tipo} en {op} "{req.colonia}" "{req.ciudad}" precio m2'
    queries = [
        base,
        f'{tipo} {op} "{req.colonia}" "{req.ciudad}" site:inmuebles24.com',
        f'{tipo} {op} "{req.colonia}" "{req.ciudad}" site:lamudi.com.mx',
        f'{tipo} {op} "{req.colonia}" "{req.ciudad}" site:propiedades.com',
        f'{tipo} {op} "{req.colonia}" "{req.ciudad}" site:vivanuncios.com.mx',
        f'{tipo} {op} "{req.colonia}" "{req.ciudad}" site:easybroker.com',
    ]
    if req.estado:
        queries.append(f'{tipo} {op} "{req.colonia}" "{req.ciudad}" "{req.estado}"')
    return queries


async def _search_google_cse(client: httpx.AsyncClient, query: str) -> List[Dict[str, Any]]:
    key = legacy_main_settings.google_cse_api_key
    cx = legacy_main_settings.google_cse_id
    if not key or not cx:
        return []
    response = await client.get(
        "https://www.googleapis.com/customsearch/v1",
        params={"key": key, "cx": cx, "q": query, "num": 10},
    )
    if response.status_code != 200:
        return []
    out = []
    for item in response.json().get("items", []) or []:
        link = item.get("link")
        if link:
            out.append({
                "title": item.get("title", ""), "url": link,
                "snippet": item.get("snippet", ""), "provider": "google_cse",
            })
    return out


async def _search_serpapi(client: httpx.AsyncClient, query: str) -> List[Dict[str, Any]]:
    key = legacy_main_settings.serpapi_api_key
    if not key:
        return []
    response = await client.get(
        "https://serpapi.com/search.json",
        params={"engine": "google", "q": query, "api_key": key, "num": 10, "hl": "es", "gl": "mx"},
    )
    if response.status_code != 200:
        return []
    out = []
    for item in response.json().get("organic_results", []) or []:
        link = item.get("link")
        if link:
            out.append({
                "title": item.get("title", ""), "url": link,
                "snippet": item.get("snippet", ""), "provider": "serpapi",
            })
    return out


async def _search_brave(client: httpx.AsyncClient, query: str) -> List[Dict[str, Any]]:
    key = legacy_main_settings.brave_search_api_key
    if not key:
        return []
    response = await client.get(
        "https://api.search.brave.com/res/v1/web/search",
        params={"q": query, "count": 10, "country": "MX", "search_lang": "es"},
        headers={"X-Subscription-Token": key, "Accept": "application/json"},
    )
    if response.status_code != 200:
        return []
    out = []
    for item in ((response.json().get("web") or {}).get("results") or []):
        link = item.get("url")
        if link:
            out.append({
                "title": item.get("title", ""), "url": link,
                "snippet": item.get("description", ""), "provider": "brave",
            })
    return out


async def _search_tavily(client: httpx.AsyncClient, query: str) -> List[Dict[str, Any]]:
    key = legacy_main_settings.tavily_api_key
    if not key:
        return []
    response = await client.post(
        "https://api.tavily.com/search",
        json={
            "api_key": key, "query": query, "search_depth": "basic",
            "max_results": 10, "include_raw_content": False,
        },
    )
    if response.status_code != 200:
        return []
    out = []
    for item in response.json().get("results", []) or []:
        link = item.get("url")
        if link:
            out.append({
                "title": item.get("title", ""), "url": link,
                "snippet": item.get("content", ""), "provider": "tavily",
            })
    return out


async def _collect_search_candidates(req: AvmWebSearchRequest) -> Dict[str, Any]:
    queries = _build_search_queries(req)
    providers_configured = {
        "google_cse": bool(legacy_main_settings.google_cse_api_key and legacy_main_settings.google_cse_id),
        "serpapi": bool(legacy_main_settings.serpapi_api_key),
        "brave": bool(legacy_main_settings.brave_search_api_key),
        "tavily": bool(legacy_main_settings.tavily_api_key),
    }
    if not any(providers_configured.values()):
        raise HTTPException(
            status_code=500,
            detail="Configura al menos una API de búsqueda: GOOGLE_CSE_API_KEY + GOOGLE_CSE_ID, SERPAPI_API_KEY, BRAVE_SEARCH_API_KEY o TAVILY_API_KEY.",
        )

    results: List[Dict[str, Any]] = []
    seen = set()
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT, follow_redirects=True) as client:
        for query in queries:
            batches = await asyncio.gather(
                _search_google_cse(client, query),
                _search_serpapi(client, query),
                _search_brave(client, query),
                _search_tavily(client, query),
                return_exceptions=True,
            )
            for batch in batches:
                if isinstance(batch, Exception):
                    continue
                for item in batch:
                    url = item.get("url", "")
                    canon = _canonical_url(url)
                    if not url or canon in seen:
                        continue
                    host = _host(url)
                    if any(bad in host for bad in BLOCKED_FETCH_DOMAINS):
                        continue
                    item["portal"] = _portal_name(url)
                    item["query"] = query
                    seen.add(canon)
                    results.append(item)
                    if len(results) >= MAX_SEARCH_RESULTS:
                        return {
                            "queries": queries,
                            "results": results,
                            "providers_configured": providers_configured,
                        }
    return {"queries": queries, "results": results, "providers_configured": providers_configured}


def _extract_json_from_text(raw: str) -> Dict[str, Any]:
    text = (raw or "").strip()

    def _try(value: str):
        try:
            return json.loads(value)
        except Exception:
            return None

    out = _try(text)
    if out is not None:
        return out

    nofence = text
    if "```" in nofence:
        first = re.search(r"```(?:json|JSON)?", nofence)
        if first:
            inner = nofence[first.end():]
            last = inner.rfind("```")
            nofence = (inner[:last] if last != -1 else inner).strip()
            out = _try(nofence)
            if out is not None:
                return out

    for source in (nofence, text):
        start = source.find("{")
        if start == -1:
            continue
        depth, in_str, esc = 0, False, False
        for index in range(start, len(source)):
            char = source[index]
            if in_str:
                if esc:
                    esc = False
                elif char == "\\":
                    esc = True
                elif char == '"':
                    in_str = False
                continue
            if char == '"':
                in_str = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    out = _try(source[start:index + 1])
                    if out is not None:
                        return out
                    break

    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        out = _try(match.group())
        if out is not None:
            return out
    raise ValueError("No se encontro un objeto JSON valido en la respuesta del modelo.")


def _extract_visible_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html or "", "html.parser")
        for tag in soup(["script", "style", "noscript", "svg", "canvas", "iframe", "header", "footer", "nav"]):
            tag.decompose()
        title = soup.title.get_text(" ", strip=True) if soup.title else ""
        meta_desc = ""
        meta = soup.find("meta", attrs={"name": "description"}) or soup.find("meta", attrs={"property": "og:description"})
        if meta and meta.get("content"):
            meta_desc = meta.get("content")
        text = soup.get_text(" ", strip=True)
        return _sameish_text(f"{title} {meta_desc} {text}")[:MAX_TEXT_CHARS_PER_URL]
    except Exception:
        return _sameish_text(re.sub(r"<[^>]+>", " ", html or ""))[:MAX_TEXT_CHARS_PER_URL]


async def _fetch_candidate_pages(candidates: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "es-MX,es;q=0.9,en;q=0.6",
    }
    sem_http = asyncio.Semaphore(3)
    sem_fc = asyncio.Semaphore(FIRECRAWL_CONCURRENCY)
    stats = {"firecrawl_calls": 0, "firecrawl_credits": 0}

    async def _try_httpx(url: str) -> Dict[str, Any]:
        async with sem_http:
            response = await fetch_public_http_result(
                url,
                timeout=FETCH_TIMEOUT,
                headers=headers,
            )
        ctype = (response.headers.get("content-type") or "").lower()
        if response.status_code >= 400 or "text/html" not in ctype:
            return {"ok": False, "status": response.status_code, "text": ""}
        return {"ok": True, "status": response.status_code, "text": _extract_visible_text(response.text)}

    async def _try_firecrawl(url: str) -> Dict[str, Any]:
        async with sem_fc:
            result = await _firecrawl_scrape(url)
        if result.get("ok"):
            stats["firecrawl_calls"] += 1
            stats["firecrawl_credits"] += int(result.get("credits") or 0)
        return result

    async def one(item: Dict[str, Any]) -> Dict[str, Any]:
        url = item.get("url", "")
        host = _host(url)
        if any(bad in host for bad in BLOCKED_FETCH_DOMAINS):
            return {**item, "fetch_status": "skipped_domain", "page_text": ""}

        is_premium = any(domain in host for domain in PREMIUM_FETCH_DOMAINS)
        try:
            if is_premium and FIRECRAWL_API_KEY:
                firecrawl = await _try_firecrawl(url)
                if firecrawl.get("ok"):
                    return {**item, "fetch_status": "ok_firecrawl", "page_text": firecrawl["page_text"]}
                try:
                    direct = await _try_httpx(url)
                    if direct["ok"]:
                        return {**item, "fetch_status": "ok_httpx_fallback", "page_text": direct["text"]}
                    return {
                        **item,
                        "fetch_status": f"firecrawl_{firecrawl.get('error','err')}__http_{direct.get('status')}",
                        "page_text": "",
                    }
                except Exception as exc:
                    return {
                        **item,
                        "fetch_status": f"firecrawl_{firecrawl.get('error','err')}__httpx_err",
                        "fetch_error": str(exc)[:120],
                        "page_text": "",
                    }

            direct = await _try_httpx(url)
            if direct["ok"]:
                return {**item, "fetch_status": "ok", "page_text": direct["text"]}

            status = direct.get("status") or 0
            if FIRECRAWL_API_KEY and (status in (403, 429) or status >= 500):
                firecrawl = await _try_firecrawl(url)
                if firecrawl.get("ok"):
                    return {
                        **item,
                        "fetch_status": f"ok_firecrawl_retry_{status}",
                        "page_text": firecrawl["page_text"],
                    }
                return {
                    **item,
                    "fetch_status": f"http_{status}__firecrawl_{firecrawl.get('error','err')}",
                    "page_text": "",
                }
            return {**item, "fetch_status": f"http_{status}", "page_text": ""}
        except Exception as exc:
            return {**item, "fetch_status": "error", "fetch_error": str(exc)[:120], "page_text": ""}

    tasks = [one(candidate) for candidate in candidates[:MAX_URLS_TO_FETCH]]
    fetched = await asyncio.gather(*tasks) if tasks else []
    if stats["firecrawl_calls"]:
        print(f"[firecrawl] calls={stats['firecrawl_calls']} credits={stats['firecrawl_credits']}")
    return fetched


def _subject_summary(req: AvmWebSearchRequest, tipo_label: str) -> str:
    partes = [
        f"{tipo_label} en {req.operacion.upper()}",
        f"Ubicación: {req.colonia}, {req.ciudad}, {req.estado}",
    ]
    if req.m2_terreno > 0:
        partes.append(
            f"Terreno: {req.m2_terreno} m²"
            + (f" ({req.condicion_terreno})" if req.condicion_terreno else "")
        )
    if req.m2_construccion > 0:
        partes.append(f"Construcción: {req.m2_construccion} m²")
    if req.recamaras > 0:
        partes.append(f"Recámaras: {req.recamaras}")
    if req.banos > 0:
        partes.append(f"Baños: {req.banos}")
    if req.estacionamientos > 0:
        partes.append(f"Estacionamientos: {req.estacionamientos}")
    if req.comentarios:
        partes.append(f"Comentarios del usuario: {req.comentarios}")
    return "\n".join(partes)


async def _claude_extract_and_value(
    req: AvmWebSearchRequest,
    tipo_label: str,
    evidence: List[Dict[str, Any]],
    queries: List[str],
    user_id: str = None,
) -> Dict[str, Any]:
    if not ANTHROPIC_API_KEY:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY no configurada")

    es_terreno = req.tipo_inmueble == "terreno"
    superficie_sujeto = req.m2_terreno if es_terreno else (req.m2_construccion or req.m2_terreno)
    evidence_compact = []
    for index, evidence_item in enumerate(evidence, 1):
        evidence_compact.append({
            "id": index,
            "titulo": evidence_item.get("title", ""),
            "url": evidence_item.get("url", ""),
            "portal": evidence_item.get("portal", ""),
            "snippet": evidence_item.get("snippet", ""),
            "fetch_status": evidence_item.get("fetch_status", ""),
            "texto_visible_limitado": evidence_item.get("page_text", "")[:MAX_TEXT_CHARS_PER_URL],
        })

    system_prompt = f"""Eres un analista valuador inmobiliario mexicano. Tu trabajo NO es inventar comparables: debes usar únicamente la evidencia web entregada por el servidor.

Objetivo: limpiar, clasificar y calcular una estimación de valor por método comparativo de mercado.

Reglas duras:
1. No inventes precios, superficies, colonias ni URLs.
2. Si un anuncio no muestra precio y superficie suficientes, márcalo como descartado.
3. Si detectas que una misma propiedad aparece duplicada, conserva una sola.
4. No uses fotos, teléfonos, nombres de asesores ni datos personales.
5. Prioriza comparables de la misma colonia/fraccionamiento; después zonas adyacentes y similares.
6. Para terrenos usa m² de terreno. Para casas/departamentos usa m² de construcción como base principal; si no hay construcción, descarta o márcalo como baja confianza.
7. Aplica factor negociación de -5% a precios de oferta en venta. En renta usa -3% si aplica.
8. Penaliza comparables sospechosos: anuncio viejo, datos incompletos, precio/m² extremo, ubicación poco clara, submercado distinto.
9. Si hay menos de 3 comparables útiles, entrega rango conservador y nivel_confianza='baja'.
10. Esta salida es una estimación de valor, no avalúo certificado.

Responde ÚNICAMENTE JSON válido con esta estructura:
{{
  "valor_estimado": 0,
  "valor_minimo": 0,
  "valor_maximo": 0,
  "valor_por_m2": 0,
  "precio_m2_base": 0,
  "nivel_confianza": "alta|media|baja",
  "razon_confianza": "",
  "resumen_ejecutivo": "",
  "comparables": [
    {{
      "descripcion": "",
      "superficie_m2": 0,
      "precio": 0,
      "precio_m2": 0,
      "fuente": "",
      "url": "",
      "incluido_en_promedio": true,
      "motivo_inclusion_o_descarte": ""
    }}
  ],
  "comparables_descartados": [
    {{"descripcion":"", "fuente":"", "url":"", "motivo":""}}
  ],
  "factores_ajuste": [
    {{"factor":"", "descripcion":"", "porcentaje":0, "impacto":"positivo|negativo|neutro"}}
  ],
  "precio_m2_ajustado_calculo": "",
  "analisis_zona": "",
  "recomendaciones": [""],
  "advertencias": "",
  "fecha": "{_today_mx()}"
}}
"""

    user_msg = {
        "inmueble_sujeto": _subject_summary(req, tipo_label),
        "superficie_relevante_sujeto_m2": superficie_sujeto,
        "queries_utilizadas": queries,
        "evidencia_web": evidence_compact,
        "instruccion_calculo": "Extrae comparables reales de la evidencia; calcula precio/m²; descarta duplicados/outliers; promedia solo incluidos; aplica ajustes; calcula valor estimado y rango.",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.post(
            f"{ANTHROPIC_BASE}/messages",
            headers={
                "x-api-key": ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": legacy_main_settings.anthropic_avm_model,
                "max_tokens": 8000,
                "temperature": 0.05,
                "system": system_prompt,
                "messages": [{"role": "user", "content": json.dumps(user_msg, ensure_ascii=False)}],
            },
        )

    if response.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Error de Claude: {response.text[:500]}")

    response_json = response.json()
    _track_anthropic(
        user_id,
        "avm",
        "/api/avm-websearch",
        response_json,
        modelo=response_json.get("model") or legacy_main_settings.anthropic_avm_model,
    )
    raw = ""
    for block in response_json.get("content", []) or []:
        if block.get("type") == "text":
            raw += block.get("text", "")
    try:
        return _extract_json_from_text(raw)
    except Exception:
        raise HTTPException(status_code=502, detail=f"Claude no devolvió JSON válido: {raw[:700]}")


@router.post("/api/avm-websearch")
async def avm_websearch(req: AvmWebSearchRequest, request: Request):
    user_id = await get_user_id_from_token(request)
    exigir_cupo(request, user_id)
    exigir_sesion(request, user_id)
    tipo_labels = {
        "casa": "Casa habitación", "departamento": "Departamento/Condominio",
        "terreno": "Terreno", "local": "Local comercial",
        "oficina": "Oficina", "bodega": "Bodega/Nave industrial",
    }
    tipo_label = tipo_labels.get(req.tipo_inmueble, req.tipo_inmueble)

    busqueda = await _collect_search_candidates(req)
    candidatos = busqueda["results"]
    if not candidatos:
        raise HTTPException(
            status_code=404,
            detail="No encontré URLs candidatas con las APIs de búsqueda configuradas. Prueba con otra colonia/zona o configura otra API de búsqueda.",
        )

    paginas = await _fetch_candidate_pages(candidatos)
    resultado = await _claude_extract_and_value(
        req,
        tipo_label,
        paginas,
        busqueda["queries"],
        user_id=user_id,
    )

    resultado["tipo_inmueble"] = tipo_label
    resultado["operacion"] = req.operacion
    resultado["colonia"] = req.colonia
    resultado["ciudad"] = req.ciudad
    resultado["estado"] = req.estado
    resultado["m2_construccion"] = req.m2_construccion
    resultado["m2_terreno"] = req.m2_terreno
    resultado["recamaras"] = req.recamaras
    resultado["banos"] = req.banos
    resultado["condicion_terreno"] = req.condicion_terreno
    resultado["timestamp"] = time.strftime("%Y-%m-%d %H:%M")
    resultado["metodologia"] = "Búsqueda web por API configurada, lectura limitada de URLs públicas, extracción mínima de datos visibles, deduplicación y clasificación por IA, cálculo comparativo con ajustes."
    resultado["fuentes_consultadas"] = [{
        "titulo": page.get("title", ""),
        "url": page.get("url", ""),
        "portal": page.get("portal", ""),
        "estado_lectura": page.get("fetch_status", ""),
        "provider": page.get("provider", ""),
    } for page in paginas]
    resultado["queries_utilizadas"] = busqueda["queries"]
    resultado["proveedores_busqueda_configurados"] = busqueda["providers_configured"]

    try:
        comps = [
            comp for comp in resultado.get("comparables", [])
            if comp.get("incluido_en_promedio") and comp.get("precio_m2")
        ]
        if comps and not resultado.get("precio_m2_base"):
            resultado["precio_m2_base"] = _round_mxn(
                sum(float(comp["precio_m2"]) for comp in comps) / len(comps),
                100,
            )
        superficie = (
            req.m2_terreno
            if req.tipo_inmueble == "terreno"
            else (req.m2_construccion or req.m2_terreno)
        )
        if superficie and resultado.get("valor_por_m2") and not resultado.get("valor_estimado"):
            resultado["valor_estimado"] = _round_mxn(
                float(resultado["valor_por_m2"]) * superficie
            )
        if resultado.get("valor_estimado"):
            valor = float(resultado["valor_estimado"])
            resultado["valor_minimo"] = resultado.get("valor_minimo") or _round_mxn(valor * 0.92)
            resultado["valor_maximo"] = resultado.get("valor_maximo") or _round_mxn(valor * 1.08)
    except Exception:
        pass

    return resultado
