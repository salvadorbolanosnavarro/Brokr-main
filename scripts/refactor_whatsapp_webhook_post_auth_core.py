#!/usr/bin/env python3
"""Delegate WhatsApp POST webhook authentication to the shared auth module."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "whatsapp.py"
OLD_IMPORT = "from routers.whatsapp_webhook_auth import meta_verify_response\n"
NEW_IMPORT = "from routers.whatsapp_webhook_auth import meta_signature_error, meta_verify_response\n"
START = '    raw = await request.body()\n\n    # Sin secreto NO se procesa nada.'
END = '    try:\n        payload = json.loads(raw)\n'
REPLACEMENT = '''    raw = await request.body()\n    auth_error = meta_signature_error(\n        raw,\n        request.headers.get("X-Hub-Signature-256", ""),\n        WA2_APP_SECRET,\n    )\n    if auth_error is not None:\n        if auth_error.status_code == 503:\n            log.error("WA_APP_SECRET y META_APP_SECRET vacíos: el webhook de WhatsApp "\n                      "queda CERRADO hasta que se configure uno de los dos en Railway.")\n        else:\n            log.warning("Firma de webhook 2.0 inválida")\n        return auth_error\n\n'''


def transform_source(source: str) -> str:
    transformed = source
    if NEW_IMPORT not in transformed:
        if OLD_IMPORT not in transformed:
            raise RuntimeError("webhook GET-auth import must be extracted first")
        transformed = transformed.replace(OLD_IMPORT, NEW_IMPORT, 1)

    if "auth_error = meta_signature_error(" in transformed:
        compile(transformed, str(TARGET), "exec")
        return transformed

    start = transformed.find(START)
    if start == -1:
        raise RuntimeError("WhatsApp POST auth block start not found")
    end = transformed.find(END, start)
    if end == -1:
        raise RuntimeError("WhatsApp POST JSON parse anchor not found")
    transformed = transformed[:start] + REPLACEMENT + transformed[end:]

    for forbidden in (
        'expected = "sha256=" + hmac.new(WA2_APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()',
        "hmac.compare_digest(sig, expected)",
    ):
        if forbidden in transformed:
            raise RuntimeError(f"legacy POST auth remains: {forbidden}")
    if "auth_error = meta_signature_error(" not in transformed:
        raise RuntimeError("POST webhook signature delegation missing")
    compile(transformed, str(TARGET), "exec")
    return transformed


def main() -> None:
    TARGET.write_text(transform_source(TARGET.read_text(encoding="utf-8")), encoding="utf-8")


if __name__ == "__main__":
    main()
