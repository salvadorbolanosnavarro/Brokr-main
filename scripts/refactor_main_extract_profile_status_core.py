from pathlib import Path

path = Path("main.py")
source = path.read_text(encoding="utf-8")

subscription_import = (
    "from core.subscriptions import (expire_trial_subscription as _expirar_trial_suscripcion, "
    "trial_has_expired as _trial_ya_vencio, trial_max_available as _trial_max_disponible)\n"
)
anchor = "from core.user_access import get_user_access_state, get_user_rol\n"
if subscription_import not in source:
    if anchor not in source:
        raise SystemExit("subscription Core import anchor not found")
    source = source.replace(anchor, anchor + subscription_import, 1)

profile_start_marker = "# ════════════════════════════════════════════════════════════════\n# Endpoint unificado para el perfil del usuario.\n"
profile_end_marker = "# ────────────────────────────────────────────\n# CLAUDE CHAT PROXY — BROQ IA SUPERINTELIGENTE\n"
profile_start = source.find(profile_start_marker)
profile_end = source.find(profile_end_marker, profile_start)
if profile_start == -1 or profile_end == -1:
    if '@app.get("/profile/status")' in source:
        raise SystemExit("profile status boundaries not found")
else:
    source = source[:profile_start] + source[profile_end:]

mount = (
    "# Estado unificado de perfil e integraciones.\n"
    "from routers.profile_status import router as profile_status_router\n"
    "app.include_router(profile_status_router)\n\n"
)
if mount not in source:
    if profile_end_marker not in source:
        raise SystemExit("profile router mount anchor not found")
    source = source.replace(profile_end_marker, mount + profile_end_marker, 1)

trial_available_start = source.find("async def _trial_max_disponible(user_id: str) -> bool:")
if trial_available_start != -1:
    trial_available_end = source.find("\n\nclass CheckoutRequest", trial_available_start)
    if trial_available_end == -1:
        raise SystemExit("trial availability boundary not found")
    source = source[:trial_available_start] + source[trial_available_end + 2:]

trial_helpers_start = source.find("def _trial_ya_vencio(trial_hasta) -> bool:")
if trial_helpers_start != -1:
    trial_helpers_end = source.find('\n\n@app.post("/subscription/trial-max")', trial_helpers_start)
    if trial_helpers_end == -1:
        raise SystemExit("trial helper boundary not found")
    source = source[:trial_helpers_start] + source[trial_helpers_end + 2:]

for forbidden in (
    '@app.get("/profile/status")',
    'async def _trial_max_disponible(user_id: str) -> bool:',
    'def _trial_ya_vencio(trial_hasta) -> bool:',
    'async def _expirar_trial_suscripcion(sub_id) -> None:',
):
    if forbidden in source:
        raise SystemExit(f"legacy profile/trial symbol remains: {forbidden}")

for required in (
    "from routers.profile_status import router as profile_status_router",
    "app.include_router(profile_status_router)",
    "expire_trial_subscription as _expirar_trial_suscripcion",
    "trial_has_expired as _trial_ya_vencio",
    "trial_max_available as _trial_max_disponible",
    '@app.get("/subscription/status")',
    '@app.post("/subscription/trial-max")',
):
    if required not in source:
        raise SystemExit(f"required profile/trial contract missing: {required}")

compile(source, "main.py", "exec")
path.write_text(source, encoding="utf-8")
