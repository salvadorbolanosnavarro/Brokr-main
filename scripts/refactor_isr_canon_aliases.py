#!/usr/bin/env python3
"""Inline ISR's legacy token aliases to Canon and remove its local :root.

The ISR token root contains aliases only; it does not own product values. This
transform replaces every var(--legacy) reference with the exact Canon token the
alias resolves to today, then removes the alias block. It refuses unknown or
remaining legacy aliases so computed design values stay equivalent.

This file is the one-shot workflow trigger while the migration is active.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "isr.html"

ALIASES = {
    "--navy": "--ink",
    "--navy-mid": "--ink-2",
    "--navy-light": "--ink-3",
    "--teal": "--ink",
    "--teal-dark": "--ink-2",
    "--teal-bg": "--paper-2",
    "--teal-border": "--line-2",
    "--white": "--bone",
    "--bg": "--bone",
    "--card": "--bone",
    "--border": "--line",
    "--border2": "--line",
    "--txt": "--ink-2",
    "--txt-soft": "--mute",
    "--txt-muted": "--mute",
    "--success-bg": "--success-soft",
    "--success-bd": "--success",
    "--danger-bg": "--danger-soft",
    "--danger-bd": "--danger",
    "--warn-bg": "--warn-soft",
    "--info-bg": "--paper-2",
    "--touch": "--touch-min",
    "--font": "--font-sans",
}

ROOT_RE = re.compile(
    r"\n:root \{\n"
    r"  --navy:.*?"
    r"  --font:\s+var\(--font-sans\);\n"
    r"\}\n",
    re.S,
)


def transform_text(source: str) -> str:
    matches = list(ROOT_RE.finditer(source))
    if len(matches) != 1:
        raise RuntimeError(f"isr.html: expected one legacy alias :root, found {len(matches)}")

    result = source
    for legacy, canon in sorted(ALIASES.items(), key=lambda item: -len(item[0])):
        result = result.replace(f"var({legacy})", f"var({canon})")
    result = ROOT_RE.sub("\n", result, count=1)

    remaining = sorted({name for name in ALIASES if f"var({name})" in result})
    if remaining:
        raise RuntimeError(f"isr.html: legacy aliases remain: {remaining}")
    if re.search(r"(?m)^\s*:root\s*\{", result):
        raise RuntimeError("isr.html: local :root remains")
    return result


def main() -> int:
    source = PATH.read_text(encoding="utf-8")
    result = transform_text(source)
    if result == source:
        raise RuntimeError("isr.html: transform produced no change")
    if "--check" not in sys.argv[1:]:
        PATH.write_text(result, encoding="utf-8")
        print("UPDATED isr.html")
    else:
        print("CHECK isr.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
