from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Recordatorios de tareas/citas en background.\nfrom routers.reminders import router as reminders_router\napp.include_router(reminders_router)\n'''
mount_block = mount_anchor + '''\n# Generación de contrato DOCX estándar.\nfrom routers.contracts_basic import router as contracts_basic_router\napp.include_router(contracts_basic_router)\n'''
if source.count('from routers.contracts_basic import router as contracts_basic_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected contracts mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.contracts_basic import router as contracts_basic_router') != 1:
    raise SystemExit("unexpected contracts mount state")

start_marker = 'class ContratoRequest(BaseModel):\n'
end_marker = '# ── CONTRATOS PERSONALIZADOS (MACHOTES) ─────────────────────────\n'
if '@app.post("/contrato")' in source:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    source = source[:start] + end_marker + source[end + len(end_marker):]
elif 'async def generar_contrato(' in source or 'class ContratoRequest(' in source:
    raise SystemExit("unexpected partially extracted standard contract block")

for legacy in ('@app.post("/contrato")', 'async def generar_contrato(', 'class ContratoRequest('):
    if legacy in source:
        raise SystemExit(f"standard contract symbol remains in main: {legacy}")
if source.count('app.include_router(contracts_basic_router)') != 1:
    raise SystemExit("standard contract router not mounted exactly once")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
