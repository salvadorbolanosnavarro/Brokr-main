#!/usr/bin/env python3
"""Remove insecure operational-secret defaults from core/config.py."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "core" / "config.py"

REPLACEMENTS = {
    'wa_register_pin=os.getenv("WA_REGISTER_PIN", "123456"),':
        'wa_register_pin=os.getenv("WA_REGISTER_PIN", "").strip(),',
    'wa2_verify_token=os.getenv("WA2_VERIFY_TOKEN", "broquer2_verify"),':
        'wa2_verify_token=os.getenv("WA2_VERIFY_TOKEN", "").strip(),',
    'wa2_register_pin=os.getenv("WA_REGISTER_PIN", "142857"),':
        'wa2_register_pin=os.getenv("WA_REGISTER_PIN", "").strip(),',
}


def transform_source(source: str) -> str:
    transformed = source
    for old, new in REPLACEMENTS.items():
        if old in transformed:
            transformed = transformed.replace(old, new, 1)
        elif new not in transformed:
            raise RuntimeError(f"config anchor not found: {old}")

    for forbidden in ('"123456"', '"broquer2_verify"', '"142857"'):
        if forbidden in transformed:
            raise RuntimeError(f"insecure WhatsApp secret default remains: {forbidden}")

    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
