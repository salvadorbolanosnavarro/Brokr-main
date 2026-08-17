#!/usr/bin/env python3
"""Absorb the final WhatsApp domain adapter into brokr-theme.css.

Preconditions:
- broquer-ui.css is the known tiny Canon-composed adapter;
- whatsapp.html is its only consumer;
- brokr-theme.css does not yet contain the adapter block.

The transform appends the domain rules to the Canon stylesheet, removes the
secondary stylesheet link from WhatsApp, and deletes broquer-ui.css. It refuses
unexpected shapes so no large legacy chat markup is otherwise touched.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "brokr-theme.css"
WA = ROOT / "whatsapp.html"
ADAPTER = ROOT / "broquer-ui.css"

EXPECTED_HEADER = "BROQUER — WhatsApp compatibility adapter"
LINK_VARIANTS = (
    '<link rel="stylesheet" href="broquer-ui.css"/>',
    '<link rel="stylesheet" href="broquer-ui.css">',
)
MARKER = "BROQUER — WhatsApp domain rules · Canon"


def build_domain_block(adapter: str) -> str:
    if EXPECTED_HEADER not in adapter:
        raise RuntimeError("broquer-ui.css: unexpected adapter content")
    start = adapter.find('/* WhatsApp-specific semantic surfaces composed from Canon. */')
    if start < 0:
        raise RuntimeError("broquer-ui.css: domain rules marker missing")
    rules = adapter[start:].strip()
    if ":root" in rules or "--bq-" in rules:
        raise RuntimeError("broquer-ui.css: adapter unexpectedly contains theme tokens")
    return (
        "\n\n/* ════════════════════════════════════════════════════════════════\n"
        f"   {MARKER}\n"
        "   Reglas de dominio del chat; consumen exclusivamente tokens Canon.\n"
        "   No definen paleta, tipografía, geometría ni chrome alternativos.\n"
        "   ════════════════════════════════════════════════════════════════ */\n"
        + rules + "\n"
    )


def transform_text(theme: str, whatsapp: str, adapter: str) -> tuple[str, str]:
    if MARKER in theme:
        raise RuntimeError("brokr-theme.css: WhatsApp domain rules already absorbed")
    domain = build_domain_block(adapter)

    matches = [variant for variant in LINK_VARIANTS if variant in whatsapp]
    if len(matches) != 1:
        raise RuntimeError(f"whatsapp.html: expected exactly one broquer-ui.css link variant, found {len(matches)}")
    link = matches[0]
    if whatsapp.count(link) != 1:
        raise RuntimeError("whatsapp.html: secondary stylesheet link is not unique")

    new_theme = theme.rstrip() + domain
    new_whatsapp = whatsapp.replace(link, '<!-- WhatsApp domain styling is part of brokr-theme.css -->', 1)

    if "broquer-ui.css" in new_whatsapp:
        raise RuntimeError("whatsapp.html: broquer-ui.css reference remains")
    if 'href="brokr-theme.css"' not in new_whatsapp:
        raise RuntimeError("whatsapp.html: Canon stylesheet missing")
    if 'body[data-app="whatsapp"]' not in new_theme:
        raise RuntimeError("brokr-theme.css: absorbed domain rules missing")
    return new_theme, new_whatsapp


def main() -> int:
    if not ADAPTER.exists():
        raise RuntimeError("broquer-ui.css: adapter file missing")
    theme = THEME.read_text(encoding="utf-8")
    whatsapp = WA.read_text(encoding="utf-8")
    adapter = ADAPTER.read_text(encoding="utf-8")
    new_theme, new_whatsapp = transform_text(theme, whatsapp, adapter)

    if "--check" in sys.argv[1:]:
        print("CHECK brokr-theme.css whatsapp.html broquer-ui.css")
        return 0

    THEME.write_text(new_theme, encoding="utf-8")
    WA.write_text(new_whatsapp, encoding="utf-8")
    ADAPTER.unlink()
    print("UPDATED brokr-theme.css whatsapp.html; DELETED broquer-ui.css")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
