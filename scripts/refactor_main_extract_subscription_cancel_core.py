from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

start = source.find('@app.post("/subscription/cancel")')
end = source.find('\n\n@app.post("/subscription/revenuecat-webhook")', start)
if start == -1 or end == -1:
    if '@app.post("/subscription/cancel")' in source:
        raise SystemExit("subscription cancel boundaries not found")
else:
    source = source[:start] + source[end + 2:]

mount = (
    '# Cancelación de suscripción web.\n'
    'from routers.subscription_cancel import router as subscription_cancel_router\n'
    'app.include_router(subscription_cancel_router)\n\n'
)
anchor = '# Estado de suscripción y trial de Broquer Max.\n'
if mount not in source:
    if anchor not in source:
        raise SystemExit("subscription cancel mount anchor not found")
    source = source.replace(anchor, mount + anchor, 1)

for forbidden in ('@app.post("/subscription/cancel")',):
    if forbidden in source:
        raise SystemExit(f"legacy subscription cancel route remains: {forbidden}")

for required in (
    'from routers.subscription_cancel import router as subscription_cancel_router',
    'app.include_router(subscription_cancel_router)',
    '@app.post("/subscription/revenuecat-webhook")',
):
    if required not in source:
        raise SystemExit(f"required cancel contract missing: {required}")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
