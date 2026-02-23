const SNAPSHOTS_SHEET = 'Snapshots';
const HIDDEN_ITEMS_SHEET = 'HiddenItems';
const PLAYERS = ['Ad The Saint', 'Sic Saint'];

function doGet() {
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const snapshotMap = readSheetMap_(ss, SNAPSHOTS_SHEET, false);
    const hiddenMap = readSheetMap_(ss, HIDDEN_ITEMS_SHEET, true);

    const players = {};
    for (const player of PLAYERS) {
      const snapshotData = snapshotMap[player] || {};
      const hiddenData = hiddenMap[player] || {};
      players[player] = {
        snapshot: snapshotData.snapshot || { items: [] },
        lastUpdatedUtc: snapshotData.lastUpdatedUtc || null,
        hidden: Array.isArray(hiddenData.hidden) ? hiddenData.hidden : [],
        hiddenLastUpdatedUtc: hiddenData.lastUpdatedUtc || null,
      };
    }

    return jsonOutput_({
      serverTimeUtc: new Date().toISOString(),
      players,
    }, 200);
  } catch (err) {
    return jsonOutput_({ ok: false, error: String(err) }, 500);
  }
}

function doPost(e) {
  try {
    const body = parsePostBody_(e);

    if (!validateSecret_(body.secret)) {
      return jsonOutput_({ ok: false, error: 'Unauthorized' }, 401);
    }

    const action = body.action;

    if (action === 'setSnapshot') {
      validatePlayer_(body.player);
      upsertJsonRow_(SNAPSHOTS_SHEET, body.player, body.snapshot);
      return jsonOutput_({ ok: true, action, player: body.player, savedAtUtc: new Date().toISOString() }, 200);
    }

    if (action === 'setHidden') {
      validatePlayer_(body.player);
      const hidden = normalizeHiddenArray_(body.hidden);
      upsertJsonRow_(HIDDEN_ITEMS_SHEET, body.player, hidden);
      return jsonOutput_({ ok: true, action, player: body.player, hidden, savedAtUtc: new Date().toISOString() }, 200);
    }

    return jsonOutput_({ ok: false, error: 'Unknown action' }, 400);
  } catch (err) {
    return jsonOutput_({ ok: false, error: String(err) }, 400);
  }
}

function validateSecret_(incoming) {
  const expected = PropertiesService.getScriptProperties().getProperty('WRITE_SECRET');
  return !!expected && incoming === expected;
}

function validatePlayer_(player) {
  if (!PLAYERS.includes(player)) {
    throw new Error('Unsupported player: ' + player);
  }
}

function parsePostBody_(e) {
  if (!e || !e.postData || !e.postData.contents) {
    throw new Error('Missing POST body');
  }

  try {
    return JSON.parse(e.postData.contents);
  } catch (err) {
    throw new Error('Invalid JSON in POST body');
  }
}

function normalizeHiddenArray_(value) {
  if (!Array.isArray(value)) return [];
  const parsed = value
    .map((entry) => Number(entry))
    .filter((entry) => Number.isInteger(entry) && entry > 0);

  return [...new Set(parsed)].sort((a, b) => a - b);
}

function readSheetMap_(ss, sheetName, expectArray) {
  const sheet = ensureSheet_(ss, sheetName);
  const lastRow = sheet.getLastRow();
  if (lastRow < 2) return {}; // row 1 is headers

  const values = sheet.getRange(2, 1, lastRow - 1, 3).getValues(); // start at row 2
  const map = {};

  for (const [player, jsonText, lastUpdatedUtc] of values) {
    if (!player) continue;
    map[player] = {
      snapshot: expectArray ? undefined : safeJsonParse_(jsonText, { items: [] }),
      hidden: expectArray ? safeJsonParse_(jsonText, []) : undefined,
      lastUpdatedUtc: lastUpdatedUtc || null,
    };
  }

  return map;
}

function safeJsonParse_(value, fallback) {
  if (value === '' || value === null || value === undefined) {
    return fallback;
  }

  try {
    return JSON.parse(value);
  } catch (err) {
    return fallback;
  }
}

function upsertJsonRow_(sheetName, player, data) {
  const ss = SpreadsheetApp.getActiveSpreadsheet();
  const sheet = ensureSheet_(ss, sheetName);
  const timestamp = new Date().toISOString();
  const payload = JSON.stringify(data || {});

  const lastRow = sheet.getLastRow();
  if (lastRow > 0) {
    const players = sheet.getRange(1, 1, lastRow, 1).getValues().flat();
    const idx = players.findIndex((name) => name === player);
    if (idx >= 0) {
      const row = idx + 1;
      sheet.getRange(row, 2, 1, 2).setValues([[payload, timestamp]]);
      return;
    }
  }

  sheet.appendRow([player, payload, timestamp]);
}

function ensureSheet_(ss, name) {
  const sheet = ss.getSheetByName(name);
  if (!sheet) {
    throw new Error('Sheet not found: ' + name);
  }
  return sheet;
}

function jsonOutput_(data, statusCode) {
  const output = ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);

  // Apps Script doesn't fully support setting HTTP status everywhere,
  // but setContent() still returns JSON consistently.
  // (Some clients may ignore statusCode.)
  // If you prefer, you can omit statusCode usage entirely.
  return output;
}
