#!/usr/bin/env python3
"""Compact only Legal's presentation markup without touching legal copy or JS."""
# One-shot migration trigger; remove this script after the guarded application.
from __future__ import annotations

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "legal.html"
CEILING = 109_324


def compact_css(css: str) -> str:
    # Legal's Canon block contains no data URLs or generated CSS strings; compact
    # formatting only. Keep declarations/selectors byte-for-byte otherwise.
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    css = re.sub(r"\s+", " ", css)
    css = re.sub(r"\s*([{}:;,])\s*", r"\1", css)
    return css.strip()


def strip_html_comments(source: str) -> str:
    """Remove ordinary non-rendered HTML comments, preserving conditional ones."""
    return re.sub(r"<!--(?!\[if\b).*?-->", "", source, flags=re.S | re.I)


def trim_source_whitespace(source: str) -> str:
    """Drop only blank source lines and trailing horizontal whitespace."""
    lines = [line.rstrip(" \t") for line in source.splitlines()]
    lines = [line for line in lines if line.strip()]
    return "\n".join(lines) + "\n"


def main() -> None:
    source = PATH.read_text(encoding="utf-8")
    match = re.search(r"<style>(.*?)</style>", source, flags=re.S)
    if not match:
        raise RuntimeError("legal.html has no inline style block")
    before = match.group(1)
    after = compact_css(before)
    transformed = source[:match.start(1)] + after + source[match.end(1):]
    transformed = strip_html_comments(transformed)
    transformed = trim_source_whitespace(transformed)
    if transformed == source:
        raise RuntimeError("Legal presentation is already compact; refusing no-op")
    final_size = len(transformed.encode("utf-8"))
    if final_size > CEILING:
        raise RuntimeError(
            f"Compacted legal.html is still {final_size} bytes; ceiling {CEILING}"
        )
    PATH.write_text(transformed, encoding="utf-8")
    print(f"legal.html: {len(source.encode('utf-8'))} -> {final_size} bytes")


if __name__ == "__main__":
    main()
