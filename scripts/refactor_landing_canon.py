#!/usr/bin/env python3
"""Move landing.html from the historical --b2-* system onto Broquer Canon.

The landing already uses Canon-equivalent values under a parallel namespace.
This transform removes that second token root/font load, adds brokr-theme.css,
and rewrites every b2 typography/color/geometry/shadow/motion reference to the
canonical token it represents. Marketing-responsive sizes remain responsive but
are expressed as clamps over Canon type tokens. This is a guarded one-shot edit.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "landing.html"

ROOT_BLOCK_RE = re.compile(
    r"\n/\* ═══ AUDIT-EXEMPT: definición de tokens del sistema .*?"
    r"/\* ═══ /AUDIT-EXEMPT ═══ \*/\n",
    re.S,
)

FONT_BLOCK = (
    '<link rel="preconnect" href="https://fonts.googleapis.com"/>\n'
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin/>\n'
    '<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:opsz,wght@14..32,400..800&display=swap"/>\n'
)

TOKEN_MAP = {
    "--b2-blue-press": "--sky-blue-press",
    "--b2-blue-deep": "--sky-navy",
    "--b2-blue-soft": "--sky-canvas",
    "--b2-blue": "--sky-blue",
    "--b2-ink": "--ink",
    "--b2-mute": "--mute",
    "--b2-paper": "--paper",
    "--b2-canvas": "--paper-2",
    "--b2-line": "--line",
    "--b2-green-soft": "--success-soft",
    "--b2-green": "--success",
    "--b2-cantera-soft": "--danger-soft",
    "--b2-cantera": "--danger",
    "--b2-on-blue": "--paper",
    "--r2-pill": "--r-pill",
    "--r2-xl": "--r-modal",
    "--r2-lg": "--r-lg",
    "--r2-sm": "--r-sm",
    "--r2": "--r",
    "--sh2-card": "--shadow-sm",
    "--sh2-lift": "--shadow-md",
    "--sh2-bar": "--shadow",
    "--sh2-media": "--shadow-lg",
    "--sh2-lg": "--shadow-lg",
    "--ease2": "--ease",
    "--fs2-caption": "--fs-label-3",
    "--fs2-sm": "--fs-sm",
    "--fs2-body": "--fs-body",
    "--fs2-lg": "--fs-body-lg",
    "--fs2-h3": "--fs-h3",
}

SPECIALS = {
    "var(--b2-on-blue-dim)": "color-mix(in srgb, var(--paper) 78%, transparent)",
    "var(--b2-on-blue-faint)": "color-mix(in srgb, var(--paper) 55%, transparent)",
    "var(--b2-line-on-blue)": "color-mix(in srgb, var(--paper) 22%, transparent)",
    "var(--fs2-h2)": "clamp(var(--fs-h2), 3.4vw, var(--fs-display))",
    "var(--fs2-h1)": "clamp(var(--fs-h1), 5.4vw, var(--fs-hero))",
    "var(--fs2-stat)": "clamp(var(--fs-h2), 3vw, var(--fs-h1))",
}


def transform_text(source: str) -> str:
    matches = list(ROOT_BLOCK_RE.finditer(source))
    if len(matches) != 1:
        raise RuntimeError(f"landing.html: expected one b2 token root block, found {len(matches)}")
    if source.count(FONT_BLOCK) != 1:
        raise RuntimeError("landing.html: expected one standalone Google Inter load")
    if 'href="brokr-theme.css"' in source:
        raise RuntimeError("landing.html: Canon stylesheet already present; transform is one-shot")

    result = source.replace(FONT_BLOCK, '<link rel="stylesheet" href="brokr-theme.css"/>\n', 1)
    result = ROOT_BLOCK_RE.sub("\n", result, count=1)
    result = result.replace(
        '<meta name="theme-color" content="#FFFFFF"/><!-- AUDIT-EXEMPT-LINE: meta no acepta var(); espejo de --b2-paper -->',
        '<meta name="theme-color" content="#FFFFFF"/><!-- AUDIT-EXEMPT-LINE: meta no acepta var(); espejo de --paper -->',
        1,
    )

    for old, new in SPECIALS.items():
        result = result.replace(old, new)
    for legacy, canon in sorted(TOKEN_MAP.items(), key=lambda item: -len(item[0])):
        result = result.replace(f"var({legacy})", f"var({canon})")

    leftovers = sorted(set(re.findall(r"--(?:b2|fs2|r2|sh2|ease2)[\w-]*", result)))
    if leftovers:
        raise RuntimeError(f"landing.html: historical visual tokens remain: {leftovers}")
    if re.search(r"(?m)^\s*:root\s*\{", result):
        raise RuntimeError("landing.html: local token root remains")
    if "fonts.googleapis.com" in result or "fonts.gstatic.com" in result:
        raise RuntimeError("landing.html: standalone Google font load remains")
    if 'href="brokr-theme.css"' not in result:
        raise RuntimeError("landing.html: Canon stylesheet missing after transform")
    return result


def main() -> int:
    source = PATH.read_text(encoding="utf-8")
    result = transform_text(source)
    if result == source:
        raise RuntimeError("landing.html: transform produced no change")
    if "--check" in sys.argv[1:]:
        print("CHECK landing.html")
    else:
        PATH.write_text(result, encoding="utf-8")
        print("UPDATED landing.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
