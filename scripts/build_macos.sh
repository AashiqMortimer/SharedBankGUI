#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python -m PyInstaller \
  --noconfirm \
  --clean \
  --windowed \
  --name BankViewer \
  --collect-submodules exporter \
  viewer_app.py

echo "Built macOS app bundle at: dist/BankViewer.app"
