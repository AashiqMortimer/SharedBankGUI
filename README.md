# RuneLite Bank Memory Export + Viewer (macOS-first)

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

## macOS setup

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

Use your iCloud shared path:

```bash
python -m exporter \
  --shared-folder "/Users/aashiqmortimer/Library/Mobile Documents/com~apple~CloudDocs/OSRS Bank Share" \
  --output-name "aashiq-bank.json" \
  --once
```

Remove `--once` to keep the exporter running with file watching.

Optional debug mode:

```bash
python -m exporter \
  --shared-folder "/Users/aashiqmortimer/Library/Mobile Documents/com~apple~CloudDocs/OSRS Bank Share" \
  --output-name "aashiq-bank.json" \
  --debug
```

Debug mode prints:

- which RuneLite config file was selected
- which `bankMemory.*` keys are present

### Exporter behavior

- Scans `~/.runelite/profiles2/**/*.properties` for files containing `bankMemory.currentList`
- If multiple matches exist, picks the **most recently modified** one
- With `--once`, performs a single export and exits
- Without `--once`, exports once immediately and keeps running
- Uses `watchdog` filesystem watch when available
- Falls back to polling every 10 seconds if watchdog is unavailable

## Run viewer GUI

In another terminal (same venv):

```bash
python -m viewer \
  --shared-folder "/Users/aashiqmortimer/Library/Mobile Documents/com~apple~CloudDocs/OSRS Bank Share" \
  --output-name "aashiq-bank.json"
```

Optional debug mode:

```bash
python -m viewer \
  --shared-folder "/Users/aashiqmortimer/Library/Mobile Documents/com~apple~CloudDocs/OSRS Bank Share" \
  --output-name "aashiq-bank.json" \
  --debug
```

### Viewer behavior

- "Auto-export on launch" is enabled by default and runs `python -m exporter --once`
- Auto-refreshes when the export JSON file changes
- Shows table rows for `itemId` + `qty` from `current`
- Shows total quantity sum
- If `current` is `null`, displays: **"No bank data yet – open bank in-game"**

## Troubleshooting

- If exporter says no bankMemory keys were found, open your OSRS bank once in RuneLite with Bank Memory plugin enabled.
- If multiple RuneLite profiles exist, exporter chooses the newest matching profile file automatically.
- If GUI doesn’t update instantly, it should still refresh on file change events; restart viewer if needed.
