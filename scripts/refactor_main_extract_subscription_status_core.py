from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

status_start = source.find('@app.get("/subscription/status")')
status_end_marker = '# ════════════════════════════════════════════════════════════════\n# Trial de Broquer Max SIN tarjeta (7 días, una sola vez por cuenta)\n'
status_end = source.find(status_end_marker, status_start)
if status_start == -1 or status_end == -1:
    if '@app.get("/subscription/status")' in source:
        raise SystemExit("subscription status boundaries not found")
else:
    source = source[:status_start] + source[status_end:]

trial_start = source.find('@app.post("/subscription/trial-max")')
trial_end = source.find('\n\n@app.post("/subscription/cancel")', trial_start)
if trial_start == -1 or trial_end == -1:
    if '@app.post("/subscription/trial-max")' in source:
        raise SystemExit("subscription trial boundaries not found")
else:
    source = source[:trial_start] + source[trial_end + 2:]

mount = (
    '# Estado de suscripción y trial de Broquer Max.\n'
    'from routers.subscription_status import router as subscription_status_router\n'
    'app.include_router(subscription_status_router)\n\n'
)
anchor = '# Estado unificado de perfil e integraciones.\n'
if mount not in source:
    if anchor not in source:
        raise SystemExit("subscription status mount anchor not found")
    source = source.replace(anchor, mount + anchor, 1)

for forbidden in (
    '@app.get("/subscription/status")',
    '@app.post("/subscription/trial-max")',
):
    if forbidden in source:
        raise SystemExit(f"legacy subscription route remains: {forbidden}")

for required in (
    'from routers.subscription_status import router as subscription_status_router',
    'app.include_router(subscription_status_router)',
    '@app.post("/subscription/checkout")',
    '@app.post("/subscription/cancel")',
):
    if required not in source:
        raise SystemExit(f"required subscription contract missing: {required}")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
