#!/usr/bin/env python3
"""Extract legacy admin read endpoints from main.py."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

START = '@app.get("/admin/me")'
END = '\n\nclass AdminRolReq(BaseModel):'
MOUNT = '''# Lecturas administrativas legacy.\nfrom routers.admin_read import router as admin_read_router\napp.include_router(admin_read_router)\n\n'''
ANCHOR = '# Estado unificado de perfil e integraciones.\n'


def transform_source(source: str) -> str:
    transformed = source
    if START in transformed:
        if transformed.count(START) != 1:
            raise RuntimeError(f"Expected one admin/me route, found {transformed.count(START)}")
        start = transformed.index(START)
        end = transformed.index(END, start)
        transformed = transformed[:start] + transformed[end + 2:]
    elif MOUNT not in transformed:
        raise RuntimeError("Admin read routes missing without router mount")

    if MOUNT not in transformed:
        idx = transformed.index(ANCHOR)
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    for marker in ('@app.get("/admin/me")', '@app.get("/admin/users")'):
        if marker in transformed:
            raise RuntimeError(f"Admin read route remains in main: {marker}")
    if 'class AdminRolReq(BaseModel):' not in transformed:
        raise RuntimeError("Admin write block removed unexpectedly")
    compile(transformed, str(MAIN), 'exec')
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding='utf-8')
    MAIN.write_text(transform_source(source), encoding='utf-8')


if __name__ == '__main__':
    main()
