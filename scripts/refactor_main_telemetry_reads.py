#!/usr/bin/env python3
"""One-shot exact refactor of main.py telemetry report reads to core.database."""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "main.py"

IMPORT_OLD = "from core.database import post_rows\n"
IMPORT_NEW = "from core.database import get_rows, post_rows\n"

USAGE_OLD = '''    # 1) usage_logs en el rango\n    usage_rows: List[Dict[str, Any]] = []\n    try:\n        async with httpx.AsyncClient(timeout=15) as client:\n            r = await client.get(\n                f"{SUPABASE_URL}/rest/v1/usage_logs",\n                headers=sb_headers,\n                params={\n                    "user_id": f"eq.{user_id}",\n                    "ts": f"gte.{desde_iso}",\n                    "select": "modulo,herramienta,proveedor,modelo,tokens_in,tokens_out,unidades,costo_usd,ts",\n                    "order": "ts.desc",\n                    "limit": "20000",\n                },\n            )\n            if r.status_code == 200:\n                usage_rows = r.json() or []\n    except Exception:\n        usage_rows = []\n'''
USAGE_NEW = '''    # 1) usage_logs en el rango\n    usage_rows: List[Dict[str, Any]] = []\n    try:\n        usage_rows = await get_rows(\n            "usage_logs",\n            {\n                "user_id": f"eq.{user_id}",\n                "ts": f"gte.{desde_iso}",\n                "select": "modulo,herramienta,proveedor,modelo,tokens_in,tokens_out,unidades,costo_usd,ts",\n                "order": "ts.desc",\n                "limit": "20000",\n            },\n            timeout=15,\n        )\n    except Exception:\n        usage_rows = []\n'''

SESSION_OLD = '''    # 2) module_sessions en el rango\n    session_rows: List[Dict[str, Any]] = []\n    try:\n        async with httpx.AsyncClient(timeout=15) as client:\n            r = await client.get(\n                f"{SUPABASE_URL}/rest/v1/module_sessions",\n                headers=sb_headers,\n                params={\n                    "user_id": f"eq.{user_id}",\n                    "ts": f"gte.{desde_iso}",\n                    "select": "modulo,segundos,ts",\n                    "limit": "50000",\n                },\n            )\n            if r.status_code == 200:\n                session_rows = r.json() or []\n    except Exception:\n        session_rows = []\n'''
SESSION_NEW = '''    # 2) module_sessions en el rango\n    session_rows: List[Dict[str, Any]] = []\n    try:\n        session_rows = await get_rows(\n            "module_sessions",\n            {\n                "user_id": f"eq.{user_id}",\n                "ts": f"gte.{desde_iso}",\n                "select": "modulo,segundos,ts",\n                "limit": "50000",\n            },\n            timeout=15,\n        )\n    except Exception:\n        session_rows = []\n'''


def replace_once(source: str, old: str, new: str, label: str) -> str:
    count = source.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, found {count}")
    return source.replace(old, new, 1)


def transform(source: str) -> str:
    updated = replace_once(source, IMPORT_OLD, IMPORT_NEW, "Core database import")
    updated = replace_once(updated, USAGE_OLD, USAGE_NEW, "usage report read")
    updated = replace_once(updated, SESSION_OLD, SESSION_NEW, "session report read")
    if "/rest/v1/usage_logs" in updated:
        raise RuntimeError("usage_logs direct REST remains")
    if "/rest/v1/module_sessions" in updated:
        raise RuntimeError("module_sessions direct REST remains")
    compile(updated, "main.py", "exec")
    return updated


def main() -> None:
    source = TARGET.read_text(encoding="utf-8")
    TARGET.write_text(transform(source), encoding="utf-8")


if __name__ == "__main__":
    main()
