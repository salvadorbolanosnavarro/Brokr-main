#!/usr/bin/env python3
"""Compact only Legal's inline Canon CSS without touching legal copy or JS."""
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


def main() -> None:
    source = PATH.read_text(encoding="utf-8")
    match = re.search(r"<style>(.*?)</style>", source, flags=re.S)
    if not match:
        raise RuntimeError("legal.html has no inline style block")
    before = match.group(1)
    after = compact_css(before)
    if after == before:
        raise RuntimeError("Legal CSS is already compact; refusing no-op")
    transformed = source[:match.start(1)] + after + source[match.end(1):]
    if len(transformed.encode("utf-8")) > CEILING:
        raise RuntimeError(
            f"Compacted legal.html is still {len(transformed.encode('utf-8'))} bytes; ceiling {CEILING}"
        )
    PATH.write_text(transformed, encoding="utf-8")
    print(
        f"legal.html: {len(source.encode('utf-8'))} -> {len(transformed.encode('utf-8'))} bytes"
    )


if __name__ == "__main__":
    main()
