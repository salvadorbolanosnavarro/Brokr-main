#!/usr/bin/env python3
"""Remove public fallback values for WhatsApp 2 operational secrets."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "core" / "config.py"

OLD_VERIFY = 'wa2_verify_token=os.getenv("WA2_VERIFY_TOKEN", "broquer2_verify"),'
NEW_VERIFY = 'wa2_verify_token=os.getenv("WA2_VERIFY_TOKEN", "").strip(),'
OLD_PIN = 'wa2_register_pin=os.getenv("WA_REGISTER_PIN", "142857"),'
NEW_PIN = 'wa2_register_pin=os.getenv("WA_REGISTER_PIN", "").strip(),'


def transform_source(source: str) -> str:
    transformed = source
    if OLD_VERIFY in transformed:
        transformed = transformed.replace(OLD_VERIFY, NEW_VERIFY, 1)
    elif NEW_VERIFY not in transformed:
        raise RuntimeError("WA2 verify-token config anchor not found")

    if OLD_PIN in transformed:
        transformed = transformed.replace(OLD_PIN, NEW_PIN, 1)
    elif NEW_PIN not in transformed:
        raise RuntimeError("WA2 register-pin config anchor not found")

    if "broquer2_verify" in transformed:
        raise RuntimeError("Public WA2 verify-token fallback remains")
    if 'wa2_register_pin=os.getenv("WA_REGISTER_PIN", "142857")' in transformed:
        raise RuntimeError("Public WA2 register-pin fallback remains")

    compile(transformed, str(CONFIG), "exec")
    return transformed


def main() -> None:
    CONFIG.write_text(transform_source(CONFIG.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
