#!/usr/bin/env python3
"""Remove public fallback values for WhatsApp operational secrets."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "core" / "config.py"

OLD_GENERAL_PIN = 'wa_register_pin=os.getenv("WA_REGISTER_PIN", "123456"),'
NEW_GENERAL_PIN = 'wa_register_pin=os.getenv("WA_REGISTER_PIN", "").strip(),'
OLD_VERIFY = 'wa2_verify_token=os.getenv("WA2_VERIFY_TOKEN", "broquer2_verify"),'
NEW_VERIFY = 'wa2_verify_token=os.getenv("WA2_VERIFY_TOKEN", "").strip(),'
OLD_WA2_PIN = 'wa2_register_pin=os.getenv("WA_REGISTER_PIN", "142857"),'
NEW_WA2_PIN = 'wa2_register_pin=os.getenv("WA_REGISTER_PIN", "").strip(),'


def _replace_or_require(source: str, old: str, new: str, label: str) -> str:
    if old in source:
        return source.replace(old, new, 1)
    if new not in source:
        raise RuntimeError(f"{label} config anchor not found")
    return source


def transform_source(source: str) -> str:
    transformed = source
    transformed = _replace_or_require(
        transformed, OLD_GENERAL_PIN, NEW_GENERAL_PIN, "WhatsApp register-pin"
    )
    transformed = _replace_or_require(
        transformed, OLD_VERIFY, NEW_VERIFY, "WA2 verify-token"
    )
    transformed = _replace_or_require(
        transformed, OLD_WA2_PIN, NEW_WA2_PIN, "WA2 register-pin"
    )

    for forbidden in (
        'wa_register_pin=os.getenv("WA_REGISTER_PIN", "123456")',
        "broquer2_verify",
        'wa2_register_pin=os.getenv("WA_REGISTER_PIN", "142857")',
    ):
        if forbidden in transformed:
            raise RuntimeError(f"Public WhatsApp operational-secret fallback remains: {forbidden}")

    compile(transformed, str(CONFIG), "exec")
    return transformed


def main() -> None:
    CONFIG.write_text(transform_source(CONFIG.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
