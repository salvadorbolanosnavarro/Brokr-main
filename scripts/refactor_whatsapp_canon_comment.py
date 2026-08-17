#!/usr/bin/env python3
"""Remove the migration-only Canon comment from whatsapp.html.

The former secondary stylesheet link was replaced with a descriptive comment.
That comment is not needed at runtime and makes the legacy large-file byte
ceiling 13 bytes worse despite eliminating an entire stylesheet. Remove exactly
that comment and nothing else so the existing architecture ceiling stays strict.
This is a guarded one-shot cleanup.
"""
from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
PATH = ROOT / "whatsapp.html"
COMMENT = '<!-- WhatsApp domain styling is part of brokr-theme.css -->'


def transform_text(source: str) -> str:
    count = source.count(COMMENT)
    if count != 1:
        raise RuntimeError(f"whatsapp.html: expected migration comment once, found {count}")
    if 'href="brokr-theme.css"' not in source:
        raise RuntimeError("whatsapp.html: Canon stylesheet missing")
    if "broquer-ui.css" in source:
        raise RuntimeError("whatsapp.html: obsolete secondary stylesheet reference returned")
    result = source.replace(COMMENT, "", 1)
    if len(result.encode("utf-8")) >= len(source.encode("utf-8")):
        raise RuntimeError("whatsapp.html: cleanup did not shrink the file")
    return result


def main() -> int:
    source = PATH.read_text(encoding="utf-8")
    result = transform_text(source)
    if "--check" in sys.argv[1:]:
        print("CHECK whatsapp.html")
    else:
        PATH.write_text(result, encoding="utf-8")
        print("UPDATED whatsapp.html")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
