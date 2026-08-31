"""Backend access to Broquer's canonical executable design system.

`brokr-theme.css` is the single source of truth for visual token values. Backend
renderers (PDFs, generated HTML, emails where appropriate) should read from this
module instead of copying color/font dictionaries into domain routers.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import re
from typing import Iterable


_THEME_PATH = Path(__file__).resolve().parent.parent / "brokr-theme.css"
_TOKEN = re.compile(r"--([A-Za-z0-9_-]+)\s*:\s*([^;]+);")


@lru_cache(maxsize=1)
def theme_css() -> str:
    """Return the canonical theme CSS, failing explicitly if it is unavailable."""
    try:
        css = _THEME_PATH.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Canonical Broquer theme is unavailable: {_THEME_PATH}") from exc
    if ":root" not in css:
        raise RuntimeError("Canonical Broquer theme does not contain a :root token block")
    return css


@lru_cache(maxsize=1)
def theme_tokens() -> dict[str, str]:
    """Parse CSS custom properties from the canonical theme."""
    tokens: dict[str, str] = {}
    for name, value in _TOKEN.findall(theme_css()):
        tokens.setdefault(name, value.strip())
    if not tokens:
        raise RuntimeError("Canonical Broquer theme does not expose CSS tokens")
    return tokens


def require_theme_tokens(names: Iterable[str]) -> dict[str, str]:
    """Return requested token values and fail if any token is missing."""
    source = theme_tokens()
    requested = [name.removeprefix("--") for name in names]
    missing = [name for name in requested if name not in source]
    if missing:
        raise RuntimeError(
            "Canonical Broquer theme is missing required tokens: " + ", ".join(missing)
        )
    return {name: source[name] for name in requested}


def pdf_palette() -> dict[str, str]:
    """Semantic token view used by backend-generated PDF documents."""
    values = require_theme_tokens(
        (
            "ink",
            "sky-navy",
            "sky-blue",
            "mute",
            "line",
            "paper-2",
            "success",
            "warn",
        )
    )
    return {
        "ink": values["ink"],
        "navy": values["sky-navy"],
        "blue": values["sky-blue"],
        "mute": values["mute"],
        "line": values["line"],
        "paper2": values["paper-2"],
        "green": values["success"],
        "orange": values["warn"],
    }
