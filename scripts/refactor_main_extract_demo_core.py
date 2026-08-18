from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

mount_anchor = '''# Finanzas: cuentas, ingresos, gastos, rentabilidad por propiedad, lectura\n# de tickets con Broq y reportes PDF/CSV. Mismo import defensivo: si falla,\n# el resto del backend sigue vivo.\ntry:\n    from routers.finanzas import router as finanzas_router\n    app.include_router(finanzas_router)\nexcept Exception as _e:\n    print(f"[finanzas] No se pudo montar el router de finanzas: {_e}")\n'''
mount_block = mount_anchor + '''\n# Solicitud pública de demos.\nfrom routers.demo import router as demo_router\napp.include_router(demo_router)\n'''
if source.count('from routers.demo import router as demo_router') == 0:
    if source.count(mount_anchor) != 1:
        raise SystemExit("unexpected demo mount anchor")
    source = source.replace(mount_anchor, mount_block, 1)
elif source.count('from routers.demo import router as demo_router') != 1:
    raise SystemExit("unexpected demo router mount state")

start_marker = '''# ════════════════════════════════════════════════════════════════\n# Agendar demo (público: landing e index) — guarda y avisa por correo\n# ════════════════════════════════════════════════════════════════\n'''
end_marker = '@app.post("/subscription/cancel")'
if start_marker in source:
    start = source.index(start_marker)
    end = source.index(end_marker, start)
    source = source[:start] + source[end:]
elif '@app.post("/demo/agendar")' in source or 'class DemoRequest(BaseModel):' in source:
    raise SystemExit("unexpected partially extracted demo state")

if source.count('@app.post("/demo/agendar")') != 0:
    raise SystemExit("demo endpoint remains in main")
if source.count('app.include_router(demo_router)') != 1:
    raise SystemExit("demo router not mounted exactly once")
compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
