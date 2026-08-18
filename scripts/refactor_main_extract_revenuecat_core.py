from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

start = source.find('@app.post("/subscription/revenuecat-webhook")')
end_marker = '# ════════════════════════════════════════════════════════════════\n# Contactos / Importar desde EasyBroker\n'
end = source.find(end_marker, start)
if start == -1 or end == -1:
    if '@app.post("/subscription/revenuecat-webhook")' in source:
        raise SystemExit("RevenueCat boundaries not found")
else:
    source = source[:start] + source[end:]

mount = (
    '# Webhook de suscripciones iOS vía RevenueCat.\n'
    'from routers.revenuecat import router as revenuecat_router\n'
    'app.include_router(revenuecat_router)\n\n'
)
anchor = '# Estado de suscripción y trial de Broquer Max.\n'
if mount not in source:
    if anchor not in source:
        raise SystemExit("RevenueCat mount anchor not found")
    source = source.replace(anchor, mount + anchor, 1)

if '@app.post("/subscription/revenuecat-webhook")' in source:
    raise SystemExit("legacy RevenueCat route remains")
for required in (
    'from routers.revenuecat import router as revenuecat_router',
    'app.include_router(revenuecat_router)',
    '# Contactos / Importar desde EasyBroker',
):
    if required not in source:
        raise SystemExit(f"required RevenueCat contract missing: {required}")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
