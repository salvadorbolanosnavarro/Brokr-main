from pathlib import Path

# This candidate was intentionally cancelled after inventorying lower main.py:
# EB_BASE and eb_headers are still used by active EasyBroker import/diagnostic
# routes. Keep this transform fail-closed so an already queued Quality run
# cannot remove live compatibility globals.
path = Path("main.py")
source = path.read_text(encoding="utf-8")
compile(source, "main.py", "exec")
raise SystemExit("cancelled: active EasyBroker routes still use EB_BASE/eb_headers")
