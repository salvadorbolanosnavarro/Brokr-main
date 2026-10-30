#!/usr/bin/env bash
# Reproducible UI checks; requires Node Playwright and a Chromium executable.
set -euo pipefail
python scripts/check_inline_scripts.py
python scripts/audit_ui_kit.py
BROQUER_STAGING_MODE=demo python scripts/build_staging.py
python scripts/serve_demo.py --port 8084 > /tmp/broquer-ui-quality.log 2>&1 &
ui_server_pid=$!
trap 'kill "$ui_server_pid" 2>/dev/null || true' EXIT
export BROQUER_TEST_URL=http://127.0.0.1:8084
node scripts/check_ui_kit.cjs
node scripts/check_ui_workflows.cjs
node scripts/check_demo.cjs
node scripts/check_country_ui.cjs
node scripts/measure_ui_application.cjs
python scripts/audit_ui_application.py
