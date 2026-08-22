#!/usr/bin/env bash
set -euo pipefail

python -m compileall -q core routers scripts \
  main.py limites.py push.py whatsapp.py admin_consola.py migrar_fotos.py
python -m unittest discover -s tests -p 'test_*.py'
python audit.py
python scripts/architecture_debt.py
