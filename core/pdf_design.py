"""Legacy-compatible PDF theme CSS bridge.

The executable source remains brokr-theme.css. This module preserves main.py's
historical fail-soft fallback so PDF generation does not fail when the theme
file is temporarily unavailable while the monolith is decomposed.
"""
from __future__ import annotations

from pathlib import Path
import re


_THEME_PATH = Path(__file__).resolve().parents[1] / "brokr-theme.css"
_theme_tokens_cache: str | None = None

_THEME_TOKENS_FALLBACK = """
  --paper:#FFFFFF; --paper-2:#F4F6FB; --bone:#FFFFFF; --shell:#F5F7FC;
  --ink:#0B0B0F; --ink-2:#2A3142; --ink-3:#57607A;
  --mute:#57607A; --mute-2:#8A93A9; --mute-3:#C6CCDA;
  --line:#E7EBF4; --line-2:#DBE1EE; --line-3:#BEC7DA;
  --forest:#0A5DE0; --forest-2:#084BB8; --forest-soft:rgba(10,93,224,0.10);
  --sky-navy:#081C4E; --sky-navy-mid:#10307E; --sky-navy-deep:#050F2E;
  --sky-blue:#0A5DE0; --sky-blue-press:#084BB8; --sky-blue-lift:#6F9FF2;
  --sky-canvas:#E9F0FD; --sky-blue-on-dark:#8FB0F5;
  --warn:#B34E0B; --warn-soft:rgba(243,116,13,0.14);
  --danger:#D42A62; --danger-soft:rgba(212,42,98,0.12);
  --success:#0E9F6E; --success-soft:rgba(14,159,110,0.12);
  --info:#0A5DE0; --info-soft:rgba(10,93,224,0.10);
  --r-xs:8px; --r-sm:12px; --r:14px; --r-lg:22px; --r-xl:26px; --r-pill:999px;
  --font-sans:'Inter',-apple-system,BlinkMacSystemFont,system-ui,Roboto,'Helvetica Neue',sans-serif;
  --font-display:'Inter',-apple-system,BlinkMacSystemFont,system-ui,Roboto,sans-serif;
"""


def _theme_tokens() -> str:
    global _theme_tokens_cache
    if _theme_tokens_cache is not None:
        return _theme_tokens_cache
    try:
        css = _THEME_PATH.read_text(encoding="utf-8")
        css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
        blocks = re.findall(r":root\s*\{([^{}]*)\}", css)
        decls = "\n".join(b.strip() for b in blocks if b.strip())
        for required in ("--ink", "--sky-navy", "--sky-blue", "--font-sans"):
            if required not in decls:
                raise ValueError(f"brokr-theme.css sin {required}")
        _theme_tokens_cache = decls
    except Exception as e:
        print(f"[theme] no se pudo leer {_THEME_PATH}: {e} — usando respaldo")
        _theme_tokens_cache = _THEME_TOKENS_FALLBACK
    return _theme_tokens_cache


def theme_css_for_pdf(extra: str = "") -> str:
    return (
        "@import url('https://fonts.googleapis.com/css2?"
        "family=Inter:opsz,wght@14..32,400..800&display=swap');\n"
        ":root{\n" + _theme_tokens() + "\n}\n"
        "/* Overrides del documento impreso: el papel es blanco (el canvas\n"
        "   azul de la app no aplica) y los radios son de documento. */\n"
        ":root{\n  --paper:#FFFFFF;\n  " + extra + "\n}\n"
    )
