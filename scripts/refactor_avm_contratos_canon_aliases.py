#!/usr/bin/env python3
"""Inline AVM/Contratos legacy UI aliases to Canon and remove local token roots.

Both modules already load brokr-theme.css. Their application-level :root blocks
only rename Canon tokens. Replace every legacy var() reference with the exact
Canon token it resolves to today, then remove those alias roots. The transform
refuses unexpected shapes and may change only these two HTML files.
"""
from __future__ import annotations

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]

CONTRATOS_ALIASES = {
    "--navy": "--ink-2",
    "--navy2": "--sky-blue",
    "--navy3": "--ink-3",
    "--teal": "--sky-blue",
    "--teal2": "--sky-blue-press",
    "--tealp": "--forest-soft",
    "--gold": "--warn",
    "--silver": "--paper-2",
    "--silver2": "--line",
    "--txt": "--ink-2",
    "--mut": "--mute",
    "--wh": "--bone",
}

AVM_ALIASES = {
    "--navy": "--sky-navy",
    "--navy-mid": "--sky-navy-mid",
    "--navy2": "--sky-blue",
    "--navy3": "--sky-navy-mid",
    "--teal": "--sky-blue",
    "--teal2": "--sky-blue-press",
    "--teal-dark": "--sky-blue-press",
    "--teal-glow": "--forest-soft",
    "--silver": "--paper-2",
    "--silver2": "--line",
    "--bdr": "--line",
    "--txt": "--ink",
    "--mut": "--mute",
    "--wh": "--bone",
    "--gray": "--bone",
    "--gray2": "--paper-2",
    "--gray-100": "--paper-2",
    "--gray-600": "--mute",
    "--screen-bg": "--paper",
    "--text": "--ink",
    "--tealp": "--forest-soft",
}

CONTRATOS_ROOT_RE = re.compile(
    r"\n:root\{\n"
    r"  --navy:var\(--ink-2\);--navy2:var\(--sky-blue\);--navy3:var\(--ink-3\);\n"
    r"  --teal:var\(--sky-blue\);--teal2:var\(--sky-blue-press\);--tealp:var\(--forest-soft\);\n"
    r"  --gold:var\(--warn\);--silver:var\(--paper-2\);--silver2:var\(--line\);\n"
    r"  --txt:var\(--ink-2\);--mut:var\(--mute\);--wh:var\(--bone\);\n"
    r"\}\n"
)

AVM_ROOT_RE = re.compile(
    r"\n<style id=\"__brokr_skin_override\">\n:root \{\n"
    r"  --navy: var\(--sky-navy\) !important;.*?"
    r"  --tealp: rgba\(0,98,227,.08\) !important;\n"
    r"\}\n",
    re.S,
)


def inline_aliases(source: str, aliases: dict[str, str]) -> str:
    result = source
    # Longest names first so composite aliases are replaced before prefixes.
    for legacy, canon in sorted(aliases.items(), key=lambda item: -len(item[0])):
        result = result.replace(f"var({legacy})", f"var({canon})")
    return result


def transform_contratos(source: str) -> str:
    if len(CONTRATOS_ROOT_RE.findall(source)) != 1:
        raise RuntimeError("contratos.html: expected exactly one legacy alias :root")
    result = inline_aliases(source, CONTRATOS_ALIASES)
    result = CONTRATOS_ROOT_RE.sub("\n", result, count=1)
    remaining = [name for name in CONTRATOS_ALIASES if f"var({name})" in result]
    if remaining:
        raise RuntimeError(f"contratos.html: legacy aliases remain: {remaining}")
    if re.search(r"(?m)^\s*:root\s*\{", result):
        raise RuntimeError("contratos.html: application token root remains")
    return result


def transform_avm(source: str) -> str:
    if len(AVM_ROOT_RE.findall(source)) != 1:
        raise RuntimeError("avm.html: expected exactly one override alias :root")
    result = inline_aliases(source, AVM_ALIASES)
    # Preserve the rest of the override style while deleting only its alias root.
    result = AVM_ROOT_RE.sub('\n<style id="__brokr_skin_override">\n', result, count=1)
    remaining = [name for name in AVM_ALIASES if f"var({name})" in result]
    if remaining:
        raise RuntimeError(f"avm.html: legacy aliases remain: {remaining}")
    # The iOS safe-area root is media-scoped environment state, not a visual theme.
    roots = re.findall(r"(?m)^\s*:root\s*\{", result)
    if len(roots) > 1:
        raise RuntimeError(f"avm.html: unexpected token roots remain: {len(roots)}")
    return result


def transform_file(name: str, *, check: bool = False) -> None:
    path = ROOT / name
    source = path.read_text(encoding="utf-8")
    result = transform_avm(source) if name == "avm.html" else transform_contratos(source)
    if result == source:
        raise RuntimeError(f"{name}: transform produced no change")
    if not check:
        path.write_text(result, encoding="utf-8")
    print(f"{'CHECK' if check else 'UPDATED'} {name}")


def main() -> int:
    check = "--check" in sys.argv[1:]
    for name in ("avm.html", "contratos.html"):
        transform_file(name, check=check)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
