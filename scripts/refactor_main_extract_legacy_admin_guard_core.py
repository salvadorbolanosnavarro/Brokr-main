#!/usr/bin/env python3
"""Move main.py's legacy admin authorization helper to Core."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

START = 'async def require_admin(request: Request) -> str:'
END = '\n\n@app.get("/admin/me")'
IMPORT = 'from core.legacy_admin import require_legacy_admin as require_admin\n'
ANCHOR = 'from core.legacy_main_config import legacy_main_settings\n'


def transform_source(source: str) -> str:
    transformed = source
    if START in transformed:
        if transformed.count(START) != 1:
            raise RuntimeError(f"Expected one legacy admin helper, found {transformed.count(START)}")
        start = transformed.index(START)
        end = transformed.index(END, start)
        transformed = transformed[:start] + transformed[end + 2:]
    elif IMPORT not in transformed:
        raise RuntimeError("legacy admin helper missing without Core import")

    if IMPORT not in transformed:
        transformed = transformed.replace(ANCHOR, ANCHOR + IMPORT, 1)

    if START in transformed:
        raise RuntimeError("legacy admin helper still present in main")
    if transformed.count('require_admin(') != 5:
        raise RuntimeError(f"Expected five admin consumers, found {transformed.count('require_admin(')}")
    compile(transformed, str(MAIN), 'exec')
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding='utf-8')
    MAIN.write_text(transform_source(source), encoding='utf-8')


if __name__ == '__main__':
    main()
