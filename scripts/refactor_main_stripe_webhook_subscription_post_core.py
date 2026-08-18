#!/usr/bin/env python3
"""Route only Stripe checkout subscription creation through core.database."""
from __future__ import annotations

from pathlib import Path

# Idempotent by design: safe for repeated dry-run and apply verification.
ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''            async with httpx.AsyncClient(timeout=10) as client:\n                await client.post(\n                    f"{SUPABASE_URL}/rest/v1/suscripciones",\n                    headers={\n                        "apikey": SUPABASE_SERVICE_KEY,\n                        "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                        "Content-Type": "application/json",\n                        "Prefer": "resolution=merge-duplicates,return=minimal",\n                    },\n                    json=sb,\n                )\n'''

NEW = '''            try:\n                await post_rows(\n                    "suscripciones",\n                    sb,\n                    prefer="resolution=merge-duplicates,return=minimal",\n                    timeout=10,\n                )\n            except httpx.HTTPStatusError:\n                # Historical webhook behavior: Supabase HTTP rejections did not abort the webhook.\n                pass\n'''


def transform_source(source: str) -> str:
    marker = '@app.post("/subscription/webhook")'
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one Stripe webhook endpoint, found {source.count(marker)}")

    start = source.index(marker)
    end = source.index('\n\n@app.post("/subscription/activate")', start)
    block = source[start:end]
    old_count = block.count(OLD)
    new_count = block.count(NEW)

    if old_count == 1 and new_count == 0:
        transformed = source[:start] + block.replace(OLD, NEW, 1) + source[end:]
        compile(transformed, str(MAIN), "exec")
        return transformed
    if old_count == 0 and new_count == 1:
        compile(source, str(MAIN), "exec")
        return source
    raise RuntimeError(
        f"Unexpected Stripe webhook subscription POST state: old={old_count}, new={new_count}"
    )


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
