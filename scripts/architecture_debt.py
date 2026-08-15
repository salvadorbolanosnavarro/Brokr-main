#!/usr/bin/env python3
"""Measure Broquer architecture debt and prevent it from growing.

The baseline is ratcheted down as cleanup lands in PR #44. These limits are
ceilings, not targets: cleanup should make every number go down. CI fails if a
legacy pattern count grows beyond the latest verified baseline.
"""
from __future__ import annotations

from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".venv", "venv", "tests", "core", "scripts", "migrations"}
CODE_SUFFIXES = {".py", ".js", ".html", ".css"}

PATTERNS = {
    "direct_env_reads": re.compile(r"\bos\.(?:getenv|environ)\b"),
    "duplicated_auth_helpers": re.compile(
        r"(?:async\s+def\s+get_user_id_from_token|async\s+def\s+_get_user_id|async\s+def\s+_user_id_desde_token)\s*\("
    ),
    "service_key_fallbacks": re.compile(
        r"SUPABASE_SERVICE_KEY\s*=.*\bor\b.*(?:SUPABASE_KEY|SUPABASE_ANON_KEY)"
    ),
    # Legacy anti-pattern: a webhook secret is checked only when configured,
    # making the endpoint public when the server variable is absent.
    "fail_open_webhook_secrets": re.compile(
        r"\bif\s+CORREO_WEBHOOK_TOKEN\s*:"
    ),
    # Legacy paid-feature policy documented in old routers as intentionally
    # fail-open. Core entitlements are fail-closed; this count must remain 0.
    "fail_open_entitlements": re.compile(
        r"Falla\s+ABIERTO",
        re.IGNORECASE,
    ),
}

# Ratcheted after verified cleanup runs. These are maximums, never goals.
BASELINE_MAX = {
    "direct_env_reads": 7,
    "duplicated_auth_helpers": 7,
    "service_key_fallbacks": 6,
    "fail_open_webhook_secrets": 0,
    "fail_open_entitlements": 0,
}
MAX_LARGE_CODE_FILES = 10


def _excluded(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return any(part in EXCLUDED_PARTS for part in relative.parts)


def python_files() -> list[Path]:
    return sorted(
        path
        for path in ROOT.rglob("*.py")
        if path.is_file() and not _excluded(path)
    )


def findings() -> dict[str, list[str]]:
    result = {name: [] for name in PATTERNS}
    for path in python_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = str(path.relative_to(ROOT))
        for name, pattern in PATTERNS.items():
            if pattern.search(text):
                result[name].append(relative)
    return result


def large_code_files() -> list[tuple[str, int]]:
    result = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix.lower() not in CODE_SUFFIXES or _excluded(path):
            continue
        size = path.stat().st_size
        if size >= 100_000:
            result.append((str(path.relative_to(ROOT)), size))
    return sorted(result, key=lambda item: item[1], reverse=True)


def main() -> int:
    debt = findings()
    failures: list[str] = []

    print("Broquer architecture debt inventory")
    print("===================================")
    for name, paths in debt.items():
        count = len(paths)
        ceiling = BASELINE_MAX[name]
        print(f"{name}: {count} (ceiling {ceiling})")
        for path in paths:
            print(f"  - {path}")
        if count > ceiling:
            failures.append(f"{name} grew from ceiling {ceiling} to {count}")

    big = large_code_files()
    print(f"large_code_files_100kb_plus: {len(big)} (ceiling {MAX_LARGE_CODE_FILES})")
    for path, size in big:
        print(f"  - {path}: {size:,} bytes")
    if len(big) > MAX_LARGE_CODE_FILES:
        failures.append(
            "large code files grew from ceiling "
            f"{MAX_LARGE_CODE_FILES} to {len(big)}"
        )

    if failures:
        print("\nArchitecture debt regression detected:")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("\nArchitecture debt guard passed: debt did not grow.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
