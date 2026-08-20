#!/usr/bin/env python3
"""Extract destructive admin deletion code from main.py without executing it."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAIN = ROOT / "main.py"

START = 'class AdminEliminarReq(BaseModel):'
END = '\n\n@app.get("/admin/user/{user_id}/uso")'
MOUNT = '''# Eliminación administrativa total (aislada; nunca se invoca en la auditoría).\nfrom routers.admin_delete import router as admin_delete_router\napp.include_router(admin_delete_router)\n\n'''
ANCHOR = '# Mutaciones administrativas no destructivas.\n'


def transform_source(source: str) -> str:
    transformed = source
    if START in transformed:
        if transformed.count(START) != 1:
            raise RuntimeError(f"Expected one AdminEliminarReq block, found {transformed.count(START)}")
        start = transformed.index(START)
        end = transformed.index(END, start)
        transformed = transformed[:start] + transformed[end + 2:]
    elif MOUNT not in transformed:
        raise RuntimeError("Admin delete block missing without router mount")

    if MOUNT not in transformed:
        if ANCHOR in transformed:
            idx = transformed.index(ANCHOR)
        elif '# Lecturas administrativas legacy.\n' in transformed:
            idx = transformed.index('# Lecturas administrativas legacy.\n')
        else:
            idx = transformed.index('# Estado unificado de perfil e integraciones.\n')
        transformed = transformed[:idx] + MOUNT + transformed[idx:]

    for marker in (
        'class AdminEliminarReq(BaseModel):',
        '@app.post("/admin/user/eliminar")',
        'async def _storage_rutas_fotos_de_usuario(',
        'async def _storage_borrar_carpeta_usuario(',
    ):
        if marker in transformed:
            raise RuntimeError(f"Admin delete implementation remains in main: {marker}")
    if '@app.get("/admin/user/{user_id}/uso")' not in transformed:
        raise RuntimeError("Admin usage endpoint removed unexpectedly")
    compile(transformed, str(MAIN), 'exec')
    return transformed


def main() -> None:
    source = MAIN.read_text(encoding='utf-8')
    MAIN.write_text(transform_source(source), encoding='utf-8')


if __name__ == '__main__':
    main()
