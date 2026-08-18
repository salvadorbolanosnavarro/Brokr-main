from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Generación de contrato DOCX estándar.\nfrom routers.contracts_basic import router as contracts_basic_router\napp.include_router(contracts_basic_router)\n'''
mount_block = mount_anchor + '''\n# Contratos personalizados (machotes).\nfrom routers.machotes import router as machotes_router\napp.include_router(machotes_router)\n'''
if source.count('from routers.machotes import router as machotes_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected machotes mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.machotes import router as machotes_router') != 1:
    raise SystemExit("unexpected machotes mount state")

start_marker = '# ── CONTRATOS PERSONALIZADOS (MACHOTES) ─────────────────────────\n'
end_marker = '# ── PDF GENERATION ──────────────────────────────────────────────\n'
if '@app.post("/contrato/machote/abrir")' in source:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    source = source[:start] + end_marker + source[end + len(end_marker):]
elif 'async def abrir_machote(' in source or 'MACHOTES_BUCKET = ' in source:
    raise SystemExit("unexpected partially extracted machotes block")

for legacy in (
    '@app.post("/contrato/machote/abrir")',
    '@app.post("/contrato/machote/sugerir")',
    '@app.post("/contrato/machote/crear")',
    '@app.get("/contrato/machotes")',
    '@app.get("/contrato/machote/{machote_id}")',
    '@app.patch("/contrato/machote/{machote_id}")',
    '@app.post("/contrato/machote/{machote_id}/preview")',
    '@app.post("/contrato/machote/{machote_id}/generar")',
    '@app.delete("/contrato/machote/{machote_id}")',
    'async def _machote_o_404(',
    'MACHOTES_BUCKET = ',
):
    if legacy in source:
        raise SystemExit(f"machotes symbol remains in main: {legacy}")
if source.count('app.include_router(machotes_router)') != 1:
    raise SystemExit("machotes router not mounted exactly once")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
