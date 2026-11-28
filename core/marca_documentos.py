"""Marca de los documentos que genera el servidor (fichas, informes).

Broquer y Cecil comparten backend. Cada frontend indica su marca al pedir un
documento ("brand": "cecil"); sin indicación, el documento sale como Broquer,
igual que siempre. Solo cambia la presentación: nombre, logo y colores.
"""
from __future__ import annotations

import base64
from functools import lru_cache
from pathlib import Path

_ASSETS = Path(__file__).resolve().parent / "marca_assets"
_ROOT = Path(__file__).resolve().parents[1]

MARCAS = {
    "broquer": {
        "clave": "broquer",
        "nombre": "Broquer",
        "logo": _ROOT / "logotipo-white.png",
        "logo_sobre_foto_chip": False,
        "color": None,          # usa los tokens de brokr-theme.css
        "tinta": "#14213d",
        "fuentes": "",
        "css": "",
    },
    "cecil": {
        "clave": "cecil",
        "nombre": "Cecil",
        "logo": _ASSETS / "cecil-wordmark.png",
        # El wordmark es naranja: sobre la foto de portada va en una pastilla blanca.
        "logo_sobre_foto_chip": True,
        "color": "#F26A1B",
        "tinta": "#191C1F",
        # @import must open the stylesheet; the token overrides go after the theme.
        "fuentes": "@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');\n",
        "css": (
            ":root{--sky-navy:#191C1F;--sky-navy-mid:#2B3137;--sky-navy-deep:#191C1F;"
            "--sky-blue:#F26A1B;--sky-blue-press:#D9550A;--sky-blue-lift:#FFC7A3;--sky-canvas:#FFF3EA;"
            "--forest:#F26A1B;--forest-2:#D9550A;--forest-soft:rgba(242,106,27,.10);--info:#F26A1B;"
            "--font-sans:'Manrope',-apple-system,BlinkMacSystemFont,system-ui,sans-serif;"
            "--font-display:'Manrope',-apple-system,BlinkMacSystemFont,system-ui,sans-serif}\n"
        ),
    },
}


def marca(valor: str | None) -> dict:
    """Marca pedida; cualquier valor desconocido es Broquer."""
    return MARCAS.get(str(valor or "").strip().lower(), MARCAS["broquer"])


@lru_cache(maxsize=8)
def _data_uri(path: str) -> str:
    try:
        return "data:image/png;base64," + base64.b64encode(Path(path).read_bytes()).decode()
    except Exception:
        return ""


def logo_data_uri(m: dict) -> str:
    return _data_uri(str(m["logo"]))


def sin_azul(css: str, m: dict) -> str:
    """Sombras y velos con tinte azul de Broquer pasan a tinta neutra en Cecil."""
    if m["clave"] != "cecil":
        return css
    for viejo, nuevo in (("0,20,59", "25,28,31"), ("5,32,60", "25,28,31")):
        css = css.replace(viejo, nuevo)
    return css
