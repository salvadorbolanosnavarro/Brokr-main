#!/usr/bin/env python3
"""Remove obsolete per-page sidebar chrome from Contactos and Leads.

The visible application shell is owned by app-shell.js. These two legacy pages
still carry a hidden sidebar copy plus CSS for that copy. This transform removes
only those two exact legacy regions and refuses to run if the expected shape is
not present exactly once.

This file is also the one-shot workflow trigger while the migration is active.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
TARGETS = ("contactos.html", "leads.html")

CSS_RE = re.compile(
    r"\n/\* ── Sidebar nav \(desktop\) — owned by app-shell\.js ─ \*/\n"
    r"\.app-shell \{ display: flex; height: 100vh; \}\n"
    r"\.app-sidebar \{.*?"
    r"\.app-content \{ flex: 1; display: flex; flex-direction: column; min-width: 0; \}\n",
    re.S,
)

HIDDEN_RE = re.compile(
    r"\n<!-- shell-replaced-sidebar -->\n"
    r"<div style=\"display:none\" hidden>\n"
    r"  <aside class=\"app-sidebar\">.*?"
    r"  </aside>\n"
    r"</div>\n",
    re.S,
)


def transform_text(source: str, name: str) -> str:
    css_matches = list(CSS_RE.finditer(source))
    hidden_matches = list(HIDDEN_RE.finditer(source))
    if len(css_matches) != 1:
        raise RuntimeError(f"{name}: expected exactly one legacy sidebar CSS block, found {len(css_matches)}")
    if len(hidden_matches) != 1:
        raise RuntimeError(f"{name}: expected exactly one hidden sidebar block, found {len(hidden_matches)}")

    result = CSS_RE.sub("\n", source, count=1)
    result = HIDDEN_RE.sub("\n", result, count=1)

    if ".app-sidebar" in result or "shell-replaced-sidebar" in result:
        raise RuntimeError(f"{name}: legacy sidebar residue remains after transform")
    return result


def transform_file(path: Path, *, check: bool = False) -> bool:
    source = path.read_text(encoding="utf-8")
    result = transform_text(source, path.name)
    changed = result != source
    if not changed:
        raise RuntimeError(f"{path.name}: transform produced no change")
    if not check:
        path.write_text(result, encoding="utf-8")
    return changed


def main() -> int:
    check = "--check" in sys.argv[1:]
    for name in TARGETS:
        transform_file(ROOT / name, check=check)
        print(f"{'CHECK' if check else 'UPDATED'} {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
