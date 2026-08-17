#!/usr/bin/env python3
"""Remove Image Cleaner's legacy visual aliases and hidden sidebar copy.

The module already loads brokr-theme.css and app-shell.js. Its local :root only
renames Canon tokens, while the hidden sidebar is obsolete shell markup. Inline
the aliases to their current Canon values and delete only those two regions.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "image-cleaner.html"

ALIASES = {
    "--navy": "--sky-navy",
    "--navy2": "--sky-navy-mid",
    "--teal": "--sky-blue",
    "--teal-dark": "--sky-blue-press",
    "--teal-bg": "--forest-soft",
    "--teal-border": "--line-2",
    "--white": "--bone",
    "--bg": "--paper",
    "--gray": "--bone",
    "--gray2": "--line",
    "--txt": "--ink",
    "--mut": "--mute",
    "--mut2": "--mute-3",
    "--red": "--danger",
    "--green": "--success",
}

ROOT_RE = re.compile(
    r"\n/\* Alias locales remapeados 1:1 al sistema Broquer \(no inventar colores\)\. \*/\n"
    r":root\{\n"
    r"  --navy:var\(--sky-navy\);--navy2:var\(--sky-navy-mid\);--teal:var\(--sky-blue\);--teal-dark:var\(--sky-blue-press\);\n"
    r"  --teal-bg:var\(--forest-soft\);--teal-border:var\(--line-2\);\n"
    r"  --white:var\(--bone\);--bg:var\(--paper\);--gray:var\(--bone\);--gray2:var\(--line\);\n"
    r"  --txt:var\(--ink\);--mut:var\(--mute\);--mut2:var\(--mute-3\);\n"
    r"  --red:var\(--danger\);--green:var\(--success\);\n"
    r"  --shadow:var\(--shadow-sm\);\n"
    r"\}\n"
)

HIDDEN_RE = re.compile(
    r"\n<!-- shell-replaced-sidebar -->\n"
    r"<div style=\"display:none\" hidden>\n"
    r"  <aside class=\"app-sidebar\">.*?"
    r"  </aside>\n"
    r"</div>\n",
    re.S,
)


def transform_text(source: str) -> str:
    if len(ROOT_RE.findall(source)) != 1:
        raise RuntimeError("image-cleaner.html: expected exactly one legacy alias root")
    if len(HIDDEN_RE.findall(source)) != 1:
        raise RuntimeError("image-cleaner.html: expected exactly one hidden sidebar copy")

    result = source
    # Replace longer aliases before their prefixes to keep the rewrite exact.
    for legacy, canon in sorted(ALIASES.items(), key=lambda item: -len(item[0])):
        result = result.replace(f"var({legacy})", f"var({canon})")
    result = result.replace("var(--shadow)", "var(--shadow-sm)")
    result = ROOT_RE.sub("\n", result, count=1)
    result = HIDDEN_RE.sub("\n", result, count=1)

    remaining = [name for name in ALIASES if f"var({name})" in result]
    if remaining:
        raise RuntimeError(f"image-cleaner.html: legacy aliases remain: {remaining}")
    if re.search(r"(?m)^\s*:root\s*\{", result):
        raise RuntimeError("image-cleaner.html: local token root remains")
    if "shell-replaced-sidebar" in result or ".app-sidebar" in result:
        raise RuntimeError("image-cleaner.html: hidden shell residue remains")
    return result


def main() -> int:
    source = PATH.read_text(encoding="utf-8")
    result = transform_text(source)
    if result == source:
        raise RuntimeError("image-cleaner.html: transform produced no change")
    if "--check" not in sys.argv[1:]:
        PATH.write_text(result, encoding="utf-8")
        print("UPDATED image-cleaner.html")
    else:
        print("CHECK image-cleaner.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
