# RuneLite Bank Memory Export + Viewer

This repo contains two Python 3.11+ tools:

1. **Exporter** (`python -m exporter`)  
   Reads RuneLite `bankMemory` plugin config from `~/.runelite/profiles2/**/*.properties` and writes a normalized JSON export.
2. **Viewer** (`python -m viewer`)  
   Simple GUI (PySide6) to display current bank item IDs and quantities from the export file.

## What gets exported

The exporter reads these ConfigManager keys under group `bankMemory`:

- `bankMemory.currentList`
- `bankMemory.snapshotList`
- `bankMemory.nameMap`

Values are parsed as JSON and exported to:

```json
{
  "exportedAt": "<ISO8601>",
  "source": {
    "os": "macOS",
    "profile": "<profile name or file>",
    "configFile": "<path>"
  },
  "current": null,
  "snapshots": [],
  "nameMap": {}
}
```

## Development setup

### 1) Create and activate virtualenv

```bash
cd /workspace/SharedBankGUI
python3.11 -m venv .venv
source .venv/bin/activate
```

### 2) Install dependencies

```bash
pip install -r requirements.txt
```

## Run exporter (optional)

The viewer can launch one-shot exports automatically on startup. You can still run the exporter manually for continuous sync.

```bash
python -m exporter \
  --shared-folder "/path/to/shared/folder" \
  --output-name "aashiq-bank.json" \
  --once
```

Remove `--once` to keep the exporter running with file watching.

## Run viewer GUI

```bash
python -m viewer \
  --shared-folder "/path/to/shared/folder" \
  --output-name "aashiq-bank.json"
```

## Packaging with PyInstaller

The packaged viewer includes the exporter module and keeps **Auto-export on launch** working without a separate exporter binary.

### macOS: build `.app`

1. Create/activate a virtual environment and install runtime deps:

   ```bash
   python3.11 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Install PyInstaller:

   ```bash
   pip install pyinstaller
   ```

3. Run the macOS build script:

   ```bash
   ./scripts/build_macos.sh
   ```

   The build uses a top-level `viewer_app.py` entrypoint so PyInstaller starts the viewer with absolute imports (avoids macOS app launch failures from package-relative entrypoints).

4. Output artifact:

   - `dist/BankViewer.app`

### Windows: build `.exe`

1. Open **Command Prompt** in repo root.
2. Create/activate a virtual environment and install deps:

   ```bat
   py -3.11 -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   pip install pyinstaller
   ```

3. Run the Windows build script:

   ```bat
   scripts\build_windows.bat
   ```

4. Output artifact:

   - `dist\BankViewer\BankViewer.exe`

## Exporter behavior

- Scans `~/.runelite/profiles2/**/*.properties` for files containing `bankMemory.currentList`
- If multiple matches exist, picks the **most recently modified** one
- With `--once`, performs a single export and exits
- Without `--once`, exports once immediately and keeps running
- Uses `watchdog` filesystem watch when available
- Falls back to polling every 10 seconds if watchdog is unavailable

## Viewer behavior

- **Auto-export on launch** is enabled by default
- In source runs: auto-export uses `python -m exporter --once`
- In packaged runs: auto-export uses the embedded exporter module directly
- Auto-refreshes when the export JSON file changes
- Shows table rows for `itemId` + `qty` from the selected save
- Shows total quantity sum

## Troubleshooting

- If exporter says no bankMemory keys were found, open your OSRS bank once in RuneLite with Bank Memory plugin enabled.
- If multiple RuneLite profiles exist, exporter chooses the newest matching profile file automatically.
- If GUI doesn’t update instantly, it should still refresh on file change events; restart viewer if needed.
