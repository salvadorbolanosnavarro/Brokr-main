#!/usr/bin/env python3
"""Remove obsolete shell/sidebar remnants from ISR and Propiedades.

Both pages already delegate visible navigation to app-shell.js. Propiedades
still carries the old complete sidebar CSS block; ISR carries only a residual
.app-sidebar skin rule plus the hidden sidebar markup. Refuse unexpected shapes.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

PROP_CSS_RE = re.compile(
    r"\n/\* ── Sidebar nav \(desktop\) ─+ \*/\n"
    r"\.app-shell \{ display: flex; height: 100vh; \}\n"
    r"\.app-sidebar \{.*?"
    r"\.app-content \{ flex: 1; display: flex; flex-direction: column; min-width: 0; \}\n",
    re.S,
)

ISR_RULE_RE = re.compile(
    r"\n  \/\* Misc legacy \*\/\n"
    r"  \.app-sidebar \{ background:var\(--paper\)!important; border-right:1px solid var\(--line\)!important; \}\n"
)

HIDDEN_RE = re.compile(
    r"\n<!-- shell-replaced-sidebar -->\n"
    r"<div style=\"display:none\" hidden>\n"
    r"  <aside class=\"app-sidebar\">.*?"
    r"  </aside>\n"
    r"</div>\n",
    re.S,
)


def transform_propiedades(source: str) -> str:
    if len(PROP_CSS_RE.findall(source)) != 1:
        raise RuntimeError("propiedades.html: expected exactly one sidebar CSS block")
    if len(HIDDEN_RE.findall(source)) != 1:
        raise RuntimeError("propiedades.html: expected exactly one hidden sidebar block")
    result = PROP_CSS_RE.sub("\n", source, count=1)
    result = HIDDEN_RE.sub("\n", result, count=1)
    if ".app-sidebar" in result or "shell-replaced-sidebar" in result:
        raise RuntimeError("propiedades.html: sidebar residue remains")
    return result


def transform_isr(source: str) -> str:
    if len(ISR_RULE_RE.findall(source)) != 1:
        raise RuntimeError("isr.html: expected exactly one residual sidebar skin rule")
    if len(HIDDEN_RE.findall(source)) != 1:
        raise RuntimeError("isr.html: expected exactly one hidden sidebar block")
    result = ISR_RULE_RE.sub("\n  /* Misc legacy */\n", source, count=1)
    result = HIDDEN_RE.sub("\n", result, count=1)
    if ".app-sidebar" in result or "shell-replaced-sidebar" in result:
        raise RuntimeError("isr.html: sidebar residue remains")
    return result


def transform_file(name: str, *, check: bool = False) -> None:
    path = ROOT / name
    source = path.read_text(encoding="utf-8")
    result = transform_isr(source) if name == "isr.html" else transform_propiedades(source)
    if result == source:
        raise RuntimeError(f"{name}: transform produced no change")
    if not check:
        path.write_text(result, encoding="utf-8")
    print(f"{'CHECK' if check else 'UPDATED'} {name}")


def main() -> int:
    check = "--check" in sys.argv[1:]
    for name in ("isr.html", "propiedades.html"):
        transform_file(name, check=check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
