from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

start = source.find('@app.post("/subscription/activate")')
end_marker = '# ════════════════════════════════════════════════════════════════\n# Trial de Broquer Max SIN tarjeta (7 días, una sola vez por cuenta)\n'
end = source.find(end_marker, start)
if start == -1 or end == -1:
    if '@app.post("/subscription/activate")' in source:
        raise SystemExit("subscription activate boundaries not found")
else:
    source = source[:start] + source[end:]

mount = (
    '# Activación interna de suscripciones.\n'
    'from routers.subscription_activate import router as subscription_activate_router\n'
    'app.include_router(subscription_activate_router)\n\n'
)
anchor = '# Webhook de suscripciones iOS vía RevenueCat.\n'
if mount not in source:
    if anchor not in source:
        raise SystemExit("subscription activate mount anchor not found")
    source = source.replace(anchor, mount + anchor, 1)

if '@app.post("/subscription/activate")' in source:
    raise SystemExit("legacy subscription activate route remains")
for required in (
    'from routers.subscription_activate import router as subscription_activate_router',
    'app.include_router(subscription_activate_router)',
    '# Contactos / Importar desde EasyBroker',
):
    if required not in source:
        raise SystemExit(f"required activate contract missing: {required}")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
