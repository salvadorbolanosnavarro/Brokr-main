#!/usr/bin/env python3
"""One-shot exact refactor of main.py telemetry writes to core.database."""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "main.py"

IMPORT_OLD = "from core.config import settings\n"
IMPORT_NEW = "from core.config import settings\nfrom core.database import post_rows\n"

USAGE_OLD = '''    try:\n        async with httpx.AsyncClient(timeout=6) as client:\n            await client.post(\n                f"{SUPABASE_URL}/rest/v1/usage_logs",\n                headers={\n                    "apikey": SUPABASE_SERVICE_KEY,\n                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                    "Content-Type": "application/json",\n                    "Prefer": "return=minimal",\n                },\n                json=payload,\n            )\n    except Exception:\n        pass\n'''
USAGE_NEW = '''    try:\n        await post_rows(\n            "usage_logs", payload, prefer="return=minimal", timeout=6\n        )\n    except Exception:\n        pass\n'''

SESSION_OLD = '''    try:\n        async with httpx.AsyncClient(timeout=5) as client:\n            await client.post(\n                f"{SUPABASE_URL}/rest/v1/module_sessions",\n                headers={\n                    "apikey": SUPABASE_SERVICE_KEY,\n                    "Authorization": f"Bearer {SUPABASE_SERVICE_KEY}",\n                    "Content-Type": "application/json",\n                    "Prefer": "return=minimal",\n                },\n                json={"user_id": user_id, "modulo": modulo, "segundos": segs},\n            )\n    except Exception:\n        pass\n'''
SESSION_NEW = '''    try:\n        await post_rows(\n            "module_sessions",\n            {"user_id": user_id, "modulo": modulo, "segundos": segs},\n            prefer="return=minimal",\n            timeout=5,\n        )\n    except Exception:\n        pass\n'''


def _replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return source.replace(old, new, 1)


def transform(source: str) -> str:
    updated = source
    if "from core.database import post_rows\n" not in updated:
        updated = _replace_once(updated, IMPORT_OLD, IMPORT_NEW, "Core database import")
    updated = _replace_once(updated, USAGE_OLD, USAGE_NEW, "usage_logs telemetry write")
    updated = _replace_once(updated, SESSION_OLD, SESSION_NEW, "module_sessions telemetry write")

    if updated.count('/rest/v1/usage_logs') != source.count('/rest/v1/usage_logs') - 1:
        raise RuntimeError("usage_logs REST reference did not decrease exactly once")
    if updated.count('/rest/v1/module_sessions') != source.count('/rest/v1/module_sessions') - 1:
        raise RuntimeError("module_sessions REST reference did not decrease exactly once")
    compile(updated, "main.py", "exec")
    return updated


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    updated = transform(source)
    if updated == source:
        raise RuntimeError("transform produced no change")
    TARGET.write_text(updated, encoding="utf-8")


if __name__ == "__main__":
    main()
