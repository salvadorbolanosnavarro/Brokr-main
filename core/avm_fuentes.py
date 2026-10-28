"""Lo que ve la persona de las fuentes de la Opinión de valor (AVM).

Reglas de producto:
  · Solo se enlistan las páginas que SÍ se consultaron. Las que fallaron o
    no se pudieron leer no aparecen en ningún lado (ni lista, ni ligas de
    comparables, ni PDF): el usuario no tiene por qué enterarse.
  · Nada de nombres de herramientas internas o proveedores, ni de cómo se
    leyó cada página.

Se aplica en el backend al armar el resultado y otra vez al generar el PDF
(el PDF recibe el resultado desde el navegador, que pudo venir de una
versión anterior).
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable, List, Set


# Campos internos que nunca deben llegar a la persona.
CAMPOS_INTERNOS = ("firecrawl", "proveedores_busqueda_configurados")

# Frases que delatan herramientas, proveedores o bloqueos.
_INTERNO_RE = re.compile(
    r"firecrawl|scrap\w*|crawl\w*|serp\s?api|tavily|brave\s+search|exa\.ai|"
    r"bloque(?:o|os|ad[oa]s?|ar|aron|an|ó)\b|bloqueó|"
    r"\brobots?\b|captcha|proxy|anti-?bots?|"
    r"no\s+(?:se\s+)?(?:pudo|pudieron|pude|pudimos)\s+(?:leer|acceder|abrir|consultar)|"
    r"acceso\s+denegado|sin\s+acceso|cr[eé]dito\s+de\s+",
    re.IGNORECASE,
)
_ORACIONES_RE = re.compile(r"(?<=[.!?;])\s+")

_CAMPOS_TEXTO = ("advertencias", "razon_confianza", "resumen_ejecutivo", "analisis_zona",
                 "precio_m2_ajustado_calculo")


def pagina_leida(fetch_status: str) -> bool:
    """True si la página se consultó con éxito (cualquier estado "ok…")."""
    return isinstance(fetch_status, str) and fetch_status.startswith("ok")


def _normaliza_url(url: Any) -> str:
    if not isinstance(url, str):
        return ""
    return url.strip().split("#", 1)[0].rstrip("/")


def fuentes_publicas(paginas: Iterable[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Solo las páginas consultadas, sin estados ni proveedores, sin repetir."""
    vistas: Set[str] = set()
    salida: List[Dict[str, str]] = []
    for p in paginas:
        url = p.get("url", "")
        clave = _normaliza_url(url)
        if not clave or clave in vistas or not pagina_leida(p.get("fetch_status", "")):
            continue
        vistas.add(clave)
        salida.append({"titulo": p.get("title", "") or "", "url": url, "portal": p.get("portal", "") or ""})
    return salida


def urls_no_consultadas(paginas: Iterable[Dict[str, Any]]) -> Set[str]:
    return {_normaliza_url(p.get("url")) for p in paginas
            if p.get("url") and not pagina_leida(p.get("fetch_status", ""))}


def limpiar_texto(texto: Any) -> Any:
    """Quita las oraciones que hablan de herramientas, proveedores o bloqueos."""
    if not isinstance(texto, str) or not _INTERNO_RE.search(texto):
        return texto
    oraciones = [o for o in _ORACIONES_RE.split(texto) if not _INTERNO_RE.search(o)]
    return " ".join(oraciones).strip()


def sanear_resultado(resultado: Dict[str, Any], urls_ocultas: Iterable[str] = ()) -> Dict[str, Any]:
    """Deja el resultado listo para mostrarse. Se puede llamar varias veces.

    urls_ocultas: ligas que no se consultaron (se quitan de los comparables).
    Si el resultado trae el formato viejo de fuentes (con "lectura"), las que
    no se leyeron también se toman como ocultas.
    """
    if not isinstance(resultado, dict):
        return resultado
    ocultas = {_normaliza_url(u) for u in urls_ocultas if u}

    fuentes = resultado.get("fuentes_consultadas")
    if isinstance(fuentes, list):
        limpias, vistas = [], set()
        for f in fuentes:
            if not isinstance(f, dict):
                continue
            clave = _normaliza_url(f.get("url"))
            lectura = f.get("lectura")
            leida = lectura is None or (isinstance(lectura, str) and lectura.startswith("leído"))
            if f.get("estado_lectura") is not None:
                leida = leida and pagina_leida(f.get("estado_lectura") or "")
            if not leida:
                if clave:
                    ocultas.add(clave)
                continue
            if not clave or clave in vistas:
                continue
            vistas.add(clave)
            limpias.append({"titulo": limpiar_texto(f.get("titulo", "") or ""), "url": f.get("url"),
                            "portal": f.get("portal", "") or ""})
        resultado["fuentes_consultadas"] = limpias

    for campo in ("comparables", "comparables_descartados"):
        for c in resultado.get(campo) or []:
            if not isinstance(c, dict):
                continue
            if _normaliza_url(c.get("url")) in ocultas:
                c["url"] = ""
            for k in ("descripcion", "motivo", "motivo_inclusion_o_descarte", "fuente"):
                if k in c:
                    c[k] = limpiar_texto(c[k])

    for f in resultado.get("factores_ajuste") or []:
        if isinstance(f, dict) and "descripcion" in f:
            f["descripcion"] = limpiar_texto(f["descripcion"])

    if isinstance(resultado.get("recomendaciones"), list):
        resultado["recomendaciones"] = [
            r for r in (limpiar_texto(x) for x in resultado["recomendaciones"]) if r
        ]

    for campo in _CAMPOS_TEXTO:
        if campo in resultado:
            resultado[campo] = limpiar_texto(resultado[campo])

    for campo in CAMPOS_INTERNOS:
        resultado.pop(campo, None)
    return resultado
