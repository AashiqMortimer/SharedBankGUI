# Shared Bank GUI (GitHub Pages + Google Apps Script)

This repository contains a static frontend (`web/`) and a Google Apps Script backend (`apps_script/Code.gs`) for syncing and viewing RuneLite Bank Memory TSV snapshots for:

- `Ad The Saint`
- `Sic Saint`

## Backend sheet setup

Create a Google Sheet with **two tabs**:

### `Snapshots`
- Column A: `player`
- Column B: `snapshotJson`
- Column C: `lastUpdatedUtc`

### `HiddenItems`
- Column A: `player`
- Column B: `hiddenJson`
- Column C: `lastUpdatedUtc`

`hiddenJson` stores a JSON array of hidden item IDs (example: `[563,554,28924]`).

## Apps Script behavior

`apps_script/Code.gs` supports:

- `GET`: returns both snapshot data and hidden items for each player.
- `POST` with `action: "setSnapshot"`: upserts snapshot data into `Snapshots`.
- `POST` with `action: "setHidden"`: upserts hidden item IDs into `HiddenItems`.

Authentication uses script property `WRITE_SECRET`.

Safe JSON parsing is used while reading rows: malformed JSON falls back to defaults (`{items:[]}` or `[]`) instead of throwing.

## Frontend behavior (`web/`)

- Maintains per-player model:
  - `snapshot.items`
  - `hiddenIds` (Set)
  - timestamps (`lastUpdatedUtc`, `hiddenLastUpdatedUtc`, `localImportedAt`, `lastRefresh`)
- Adds a **Hidden** action column:
  - `Hide` for visible item
  - `Unhide` for hidden item
- Adds toggle: **Show hidden items** (default off)
- Adds toggle in compare: **Include hidden in compare** (default off)
- On initial load (when API URL is set) and on **Test connection**, pulls remote state and renders tables.
- Hide/unhide updates UI instantly and then persists remotely with `setHidden`.
- Snapshot sync (`setSnapshot`) does not modify hidden state.

## Deploy / run

You can host `web/` on GitHub Pages. Set your Apps Script Web App URL and write secret in the UI fields, then use **Test connection** to pull the latest server state.
