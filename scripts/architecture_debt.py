#!/usr/bin/env python3
"""Report measurable Broquer architecture debt without changing production.

This inventory is intentionally mechanical. It tracks legacy infrastructure
patterns that are being migrated into ``core/`` and makes the remaining scope
visible in CI. A later guard can freeze these counts so they only move down.
"""
from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".venv", "venv", "tests", "core", "scripts", "migrations"}

PATTERNS = {
    "direct_env_reads": re.compile(r"\bos\.(?:getenv|environ)\b"),
    "duplicated_auth_helpers": re.compile(
        r"(?:async\s+def\s+get_user_id_from_token|async\s+def\s+_get_user_id)\s*\("
    ),
    "service_key_fallbacks": re.compile(
        r"SUPABASE_SERVICE_KEY\s*=.*\bor\b.*(?:SUPABASE_KEY|SUPABASE_ANON_KEY)"
    ),
}


def python_files() -> list[Path]:
    out = []
    for path in ROOT.rglob("*.py"):
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS for part in relative.parts):
            continue
        out.append(path)
    return sorted(out)


def findings() -> dict[str, list[str]]:
    result = {name: [] for name in PATTERNS}
    for path in python_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = str(path.relative_to(ROOT))
        for name, pattern in PATTERNS.items():
            if pattern.search(text):
                result[name].append(relative)
    return result


def large_files() -> list[tuple[str, int]]:
    result = []
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(ROOT)
        if any(part in EXCLUDED_PARTS or part == ".git" for part in relative.parts):
            continue
        size = path.stat().st_size
        if size >= 100_000:
            result.append((str(relative), size))
    return sorted(result, key=lambda item: item[1], reverse=True)


def main() -> int:
    debt = findings()
    print("Broquer architecture debt inventory")
    print("===================================")
    for name, paths in debt.items():
        print(f"{name}: {len(paths)}")
        for path in paths:
            print(f"  - {path}")

    big = large_files()
    print(f"large_files_100kb_plus: {len(big)}")
    for path, size in big:
        print(f"  - {path}: {size:,} bytes")

    # Reporting only for the first run. Once the baseline is captured in CI,
    # thresholds can be enforced so these counts may decrease but never grow.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
