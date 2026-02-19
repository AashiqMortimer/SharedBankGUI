#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

python -m PyInstaller --noconfirm --clean viewer_pyinstaller.spec

echo "Built macOS app bundle at: dist/BankViewer.app"
