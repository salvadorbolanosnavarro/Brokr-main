#!/usr/bin/env python3
"""Extract legacy admin role/active mutations from main.py."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

START = 'class AdminRolReq(BaseModel):'
END = '\n\nclass AdminEliminarReq(BaseModel):'
MOUNT = '''# Mutaciones administrativas no destructivas.\nfrom routers.admin_accounts import router as admin_accounts_router\napp.include_router(admin_accounts_router)\n\n'''
ANCHOR = '# Lecturas administrativas legacy.\n'


def transform_source(source: str) -> str:
    transformed = source
    if START in transformed:
        if transformed.count(START) != 1:
            raise RuntimeError(f"Expected one AdminRolReq block, found {transformed.count(START)}")
        start = transformed.index(START)
        end = transformed.index(END, start)
        transformed = transformed[:start] + transformed[end + 2:]
    elif MOUNT not in transformed:
        raise RuntimeError("Admin account mutations missing without router mount")

    if MOUNT not in transformed:
        if ANCHOR in transformed:
            idx = transformed.index(ANCHOR)
        else:
            idx = transformed.index('# Estado unificado de perfil e integraciones.\n')
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    for marker in (
        'class AdminRolReq(BaseModel):',
        '@app.post("/admin/user/rol")',
        'class AdminActivoReq(BaseModel):',
        '@app.post("/admin/user/activo")',
    ):
        if marker in transformed:
            raise RuntimeError(f"Admin account mutation remains in main: {marker}")
    if 'class AdminEliminarReq(BaseModel):' not in transformed:
        raise RuntimeError("Destructive admin delete block removed unexpectedly")
    compile(transformed, str(MAIN), 'exec')
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding='utf-8')
    MAIN.write_text(transform_source(source), encoding='utf-8')


if __name__ == '__main__':
    main()
