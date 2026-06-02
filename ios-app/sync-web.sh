#!/bin/bash
# Copia los archivos frontend de Brokr-main-fresh/ a ios-app/www/
# Excluye backend (Python), backups, uploads, herramientas dev.
set -euo pipefail

SRC="$(cd "$(dirname "$0")/.." && pwd)"
DEST="$(cd "$(dirname "$0")" && pwd)/www"

mkdir -p "$DEST"

rsync -a --delete \
  --include='*.html' \
  --include='*.css' \
  --include='*.js' \
  --include='*.png' \
  --include='*.jpg' \
  --include='*.jpeg' \
  --include='*.svg' \
  --include='*.mp4' \
  --include='*.webp' \
  --include='*.ico' \
  --include='manifest.json' \
  --exclude='ios-app/' \
  --exclude='node_modules/' \
  --exclude='__pycache__/' \
  --exclude='_backup_pre_shell/' \
  --exclude='_entrega/' \
  --exclude='uploads/' \
  --exclude='routers/' \
  --exclude='.git/' \
  --exclude='*.py' \
  --exclude='*.sql' \
  --exclude='*.md' \
  --exclude='Dockerfile' \
  --exclude='requirements.txt' \
  --exclude='CNAME' \
  --exclude='*.jsx' \
  --exclude='design-canvas.*' \
  --exclude='ios-frame.*' \
  --exclude='macos-window.*' \
  --exclude='*' \
  "$SRC/" "$DEST/"

echo "✔ Sync completo: $(find "$DEST" -type f | wc -l | tr -d ' ') archivos en www/"
