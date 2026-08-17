#!/usr/bin/env python3
"""Inline ISR's legacy UI token aliases to Canon and remove its local UI :root.

ISR also contains an AUDIT-EXEMPT `:root` inside the generated standalone PDF
HTML. That document root is intentionally preserved. This transform targets
only the application alias root and refuses remaining UI alias definitions or
references so the app's computed design values stay equivalent.
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
        raise RuntimeError(f"isr.html: expected one legacy UI alias :root, found {len(matches)}")

    result = source
    for legacy, canon in sorted(ALIASES.items(), key=lambda item: -len(item[0])):
        result = result.replace(f"var({legacy})", f"var({canon})")
    result = ROOT_RE.sub("\n", result, count=1)

    remaining_refs = sorted({name for name in ALIASES if f"var({name})" in result})
    remaining_defs = sorted({name for name in ALIASES if re.search(rf"(?m)^\s*{re.escape(name)}\s*:", result)})
    if remaining_refs or remaining_defs:
        raise RuntimeError(
            f"isr.html: legacy UI aliases remain refs={remaining_refs} defs={remaining_defs}"
        )
    if "${_isrTokens()}" not in result:
        raise RuntimeError("isr.html: embedded PDF Canon token injection was unexpectedly changed")
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
