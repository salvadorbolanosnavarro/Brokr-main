#!/usr/bin/env python3
"""Remove the obsolete hidden sidebar copy from contratos.html only.

Visible navigation is owned by app-shell.js. The legacy hidden copy is never
shown and must not remain inside the module. Refuse any shape other than the
single expected block; this is a one-shot guarded migration.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "contratos.html"

HIDDEN_RE = re.compile(
    r"\n<!-- shell-replaced-sidebar -->\n"
    r"<div style=\"display:none\" hidden>\n"
    r"  <aside class=\"app-sidebar\">.*?"
    r"  </aside>\n"
    r"</div>\n",
    re.S,
)


def transform_text(source: str) -> str:
    matches = list(HIDDEN_RE.finditer(source))
    if len(matches) != 1:
        raise RuntimeError(f"contratos.html: expected one hidden sidebar block, found {len(matches)}")
    result = HIDDEN_RE.sub("\n", source, count=1)
    if "shell-replaced-sidebar" in result or '<aside class="app-sidebar">' in result:
        raise RuntimeError("contratos.html: hidden sidebar residue remains")
    if '<script src="app-shell.js" defer></script>' not in result:
        raise RuntimeError("contratos.html: shared app shell is missing")
    return result


def main() -> int:
    source = PATH.read_text(encoding="utf-8")
    result = transform_text(source)
    if result == source:
        raise RuntimeError("contratos.html: transform produced no change")
    if "--check" in sys.argv[1:]:
        print("CHECK contratos.html")
    else:
        PATH.write_text(result, encoding="utf-8")
        print("UPDATED contratos.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
