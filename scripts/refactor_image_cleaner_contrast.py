#!/usr/bin/env python3
"""Raise four Image Cleaner secondary-text selectors to Canon-readable contrast.

This one-shot transform changes presentation only; editor behavior is untouched.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "image-cleaner.html"

REPLACEMENTS = {
    ".drop-types{font-size:var(--fs-caption);color:var(--mute-3);margin-top:5px}":
        ".drop-types{font-size:var(--fs-caption);color:var(--mute);margin-top:5px}",
    ".prompt-hint{font-size:var(--fs-caption);color:var(--mute-3);margin-top:8px;line-height:1.5}":
        ".prompt-hint{font-size:var(--fs-caption);color:var(--mute);margin-top:8px;line-height:1.5}",
    ".card-status{font-size:var(--fs-caption);color:var(--mute-3);flex:1;font-weight:500}":
        ".card-status{font-size:var(--fs-caption);color:var(--mute);flex:1;font-weight:500}",
    ".empty{display:none;text-align:center;padding:40px 20px;color:var(--mute-3);font-size:var(--fs-sm)}":
        ".empty{display:none;text-align:center;padding:40px 20px;color:var(--mute);font-size:var(--fs-sm)}",
}


def transform_text(source: str) -> str:
    result = source
    for old, new in REPLACEMENTS.items():
        count = result.count(old)
        if count != 1:
            raise RuntimeError(f"image-cleaner.html: expected exact selector once, found {count}: {old[:40]}")
        result = result.replace(old, new, 1)
    if result == source:
        raise RuntimeError("image-cleaner.html: contrast transform produced no change")
    return result


def main() -> int:
    source = PATH.read_text(encoding="utf-8")
    result = transform_text(source)
    if "--check" in sys.argv[1:]:
        print("CHECK image-cleaner.html")
    else:
        PATH.write_text(result, encoding="utf-8")
        print("UPDATED image-cleaner.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
