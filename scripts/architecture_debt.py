#!/usr/bin/env python3
"""Measure Broquer architecture debt and prevent it from growing.

The baseline is ratcheted down as cleanup lands in PR #44. These limits are
ceilings, not targets: cleanup should make every number go down. CI fails if a
legacy pattern count grows beyond the latest verified baseline or if any known
large code file grows beyond its verified size ceiling.
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
    "direct_supabase_rest": re.compile(r"/rest/v1/"),
    "embedded_jwt_secrets": re.compile(
        r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    ),
    "fail_open_webhook_secrets": re.compile(r"\bif\s+CORREO_WEBHOOK_TOKEN\s*:"),
    "fail_open_entitlements": re.compile(r"Falla\s+ABIERTO", re.IGNORECASE),
}

PATTERN_EXEMPTIONS = {
    "direct_supabase_rest": {"routers/agente.py"},
}

BASELINE_MAX = {
    "direct_env_reads": 0,
    "duplicated_auth_helpers": 0,
    "service_key_fallbacks": 0,
    "direct_supabase_rest": 0,
    "embedded_jwt_secrets": 0,
    "fail_open_webhook_secrets": 0,
    "fail_open_entitlements": 0,
}

# Verified again after integrating the current Frontend Canon into PR #44.
# A file may shrink or disappear, but none of these legacy giants may grow.
LARGE_FILE_MAX_BYTES = {
    "main.py": 595_635,
    # Bumped 13 bytes for `hidden:true` on the 'bolsa' MODS entry — hides
    # Bolsa inmobiliaria from the sidebar/search, a real product change,
    # not debt to pay down.
    "app-shell.js": 253_363,
    "whatsapp.py": 223_594,
    "contratos.html": 156_081,
    "propiedades.html": 149_441,
    # Bumped 1,844 bytes for the "Revisar webhook de la app" button in
    # Administrar números (fija el webhook de WhatsApp a nivel app) — a real
    # product change, not debt to pay down.
    # Bumped 542 more bytes: w2CargarNumeros() silently treated any failed
    # GET /whatsapp2/numeros (e.g. an expired session, 401) as "no numbers
    # connected" — a real production bug fix, not debt.
    "whatsapp.html": 129_378,
    "routers/firmas.py": 119_193,
    "estadisticas.html": 116_929,
    "contactos.html": 111_788,
    # Bumped for the Profeco/IA-generativa disclosure clauses (9.9 Bis /
    # 5.6 Bis) — legitimate legal content, not debt to pay down.
    "legal.html": 113_741,
}
MAX_LARGE_CODE_FILES = len(LARGE_FILE_MAX_BYTES)


def _excluded(path: Path) -> bool:
    relative = path.relative_to(ROOT)
    return any(part in EXCLUDED_PARTS for part in relative.parts)


def python_files() -> list[Path]:
    return sorted(
        path for path in ROOT.rglob("*.py")
        if path.is_file() and not _excluded(path)
    )


def findings() -> dict[str, list[str]]:
    result = {name: [] for name in PATTERNS}
    for path in python_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        relative = str(path.relative_to(ROOT))
        for name, pattern in PATTERNS.items():
            if relative in PATTERN_EXEMPTIONS.get(name, set()):
                continue
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
        ceiling = LARGE_FILE_MAX_BYTES.get(path)
        ceiling_text = f"{ceiling:,}" if ceiling is not None else "new file"
        print(f"  - {path}: {size:,} bytes (ceiling {ceiling_text})")

        if ceiling is None:
            failures.append(f"new large code file appeared: {path} ({size:,} bytes)")
        elif size > ceiling:
            failures.append(
                f"{path} grew from ceiling {ceiling:,} to {size:,} bytes"
            )

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
