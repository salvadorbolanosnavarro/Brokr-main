#!/usr/bin/env python3
"""Route only Stripe customer-id persistence through core.database."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

OLD = '''    # 3. Guardar en Supabase\n    async with httpx.AsyncClient(timeout=10) as client:\n        await client.patch(\n            f"{SUPABASE_URL}/rest/v1/usuarios?id=eq.{user_id}",\n            headers={\n                "apikey": SUPABASE_SERVICE_KEY,\n                "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                "Content-Type": "application/json",\n                "Prefer": "return=minimal",\n            },\n            json={"stripe_customer_id": customer_id}\n        )\n'''

NEW = '''    # 3. Guardar en Supabase\n    try:\n        await patch_rows(\n            "usuarios",\n            {"id": f"eq.{user_id}"},\n            {"stripe_customer_id": customer_id},\n            prefer="return=minimal",\n            timeout=10,\n        )\n    except httpx.HTTPStatusError:\n        # Historical behavior: Supabase HTTP rejection did not abort customer creation.\n        pass\n'''


def transform_source(source: str) -> str:
    marker = 'async def _get_or_create_stripe_customer('
    if source.count(marker) != 1:
        raise RuntimeError(f"Expected one Stripe customer helper, found {source.count(marker)}")
    start = source.index(marker)
    end = source.index('\n\n@app.post("/subscription/checkout")', start)
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
    raise RuntimeError(f"Unexpected Stripe customer patch state: old={old_count}, new={new_count}")


def main() -> None:
    source = MAIN.read_text(encoding="utf-8")
    MAIN.write_text(transform_source(source), encoding="utf-8")


if __name__ == "__main__":
    main()
