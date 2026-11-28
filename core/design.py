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


def load_theme_tokens(path: Path) -> dict[str, str]:
    """Read local imported tokens and resolve aliases for non-browser renderers.

    Parent declarations keep the existing precedence. Remote imports are never
    fetched; imports must stay inside the theme directory.
    """
    tokens: dict[str, str] = {}
    root = path.resolve().parent
    visited: set[Path] = set()
    def collect(source: Path) -> None:
        source = source.resolve()
        source.relative_to(root)
        if source in visited:
            return
        visited.add(source)
        css = re.sub(r"/\*.*?\*/", "", source.read_text(encoding="utf-8"), flags=re.S)
        for name, value in _TOKEN.findall(css):
            tokens.setdefault(name, value.strip())
        for imported in re.findall(r"@import\s+url\([\"']([^\"']+)[\"']\)", css):
            if ":" not in imported and imported.endswith(".css"):
                collect(source.parent / imported)
    collect(path)
    if not tokens:
        raise RuntimeError("Canonical Broquer theme does not expose CSS tokens")
    resolved: dict[str, str] = {}
    reference = re.compile(r"var\(\s*--([\w-]+)(?:\s*,\s*([^()]+))?\)")
    def resolve(name: str, seen: frozenset[str] = frozenset()) -> str:
        if name in resolved:
            return resolved[name]
        if name in seen:
            raise RuntimeError("Cyclic design token: " + name)
        value = reference.sub(lambda m: resolve(m[1], seen | {name}) if m[1] in tokens else (m[2] or m[0]), tokens[name])
        resolved[name] = value
        return value
    return {name: resolve(name) for name in tokens}


@lru_cache(maxsize=1)
def theme_tokens() -> dict[str, str]:
    """Return concrete canonical token values, including local imports."""
    theme_css()
    return load_theme_tokens(_THEME_PATH)


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
