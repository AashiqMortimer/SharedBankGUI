@echo off
setlocal

set ROOT_DIR=%~dp0\..
cd /d %ROOT_DIR%

python -m PyInstaller --noconfirm --clean --windowed --name BankViewer --collect-submodules exporter viewer\__main__.py

echo Built Windows executable at: dist\BankViewer\BankViewer.exe
