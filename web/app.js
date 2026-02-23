const PLAYERS = ['Ad The Saint', 'Sic Saint'];

const state = {
  apiUrl: localStorage.getItem('apiUrl') || '',
  writeSecret: localStorage.getItem('writeSecret') || '',
  showHidden: false,
  includeHiddenCompare: false,
  players: Object.fromEntries(
    PLAYERS.map((name) => [name, {
      snapshot: { items: [] },
      hiddenIds: new Set(),
      timestamps: {
        lastUpdatedUtc: null,
        hiddenLastUpdatedUtc: null,
        localImportedAt: null,
        lastRefresh: null,
      },
    }])
  ),
};

function getVisibleItems(playerState) {
  const items = playerState.snapshot?.items || [];
  if (state.showHidden) return items;
  return items.filter((item) => !playerState.hiddenIds.has(Number(item.id)));
}

function setStatus(message) {
  document.getElementById('status').textContent = message;
}

async function fetchRemoteState() {
  const res = await fetch(state.apiUrl);
  if (!res.ok) throw new Error(`GET failed: ${res.status}`);
  const payload = await res.json();

  for (const player of PLAYERS) {
    const serverPlayer = payload.players?.[player] || {};
    const model = state.players[player];
    model.snapshot = serverPlayer.snapshot || { items: [] };
    model.hiddenIds = new Set((serverPlayer.hidden || []).map(Number));
    model.timestamps.lastUpdatedUtc = serverPlayer.lastUpdatedUtc || null;
    model.timestamps.hiddenLastUpdatedUtc = serverPlayer.hiddenLastUpdatedUtc || null;
    model.timestamps.lastRefresh = payload.serverTimeUtc || new Date().toISOString();
  }
}

async function postAction(data) {
  const res = await fetch(state.apiUrl, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...data, secret: state.writeSecret }),
  });
  if (!res.ok) throw new Error(`POST failed: ${res.status}`);
  return res.json();
}

async function setHidden(player) {
  const hidden = [...state.players[player].hiddenIds].sort((a, b) => a - b);
  await postAction({ action: 'setHidden', player, hidden });
}

function renderPlayerTables() {
  const host = document.getElementById('players');
  host.innerHTML = '';

  PLAYERS.forEach((player) => {
    const model = state.players[player];
    const items = getVisibleItems(model);
    const card = document.createElement('section');
    card.innerHTML = `
      <h2>${player}</h2>
      <div class="muted">Snapshot: ${model.timestamps.lastUpdatedUtc || 'n/a'} | Hidden: ${model.timestamps.hiddenLastUpdatedUtc || 'n/a'} | Refresh: ${model.timestamps.lastRefresh || 'n/a'}</div>
      <table>
        <thead><tr><th>Item ID</th><th>Qty</th><th>Hidden</th></tr></thead>
        <tbody>
          ${items.map((item) => {
            const id = Number(item.id);
            const hidden = model.hiddenIds.has(id);
            const label = hidden ? 'Unhide' : 'Hide';
            return `<tr><td>${id}</td><td>${item.qty ?? 0}</td><td><button data-player="${player}" data-item-id="${id}" class="hideBtn">${label}</button></td></tr>`;
          }).join('')}
        </tbody>
      </table>
    `;
    host.appendChild(card);
  });

  host.querySelectorAll('.hideBtn').forEach((btn) => {
    btn.addEventListener('click', async () => {
      const player = btn.dataset.player;
      const itemId = Number(btn.dataset.itemId);
      const hiddenSet = state.players[player].hiddenIds;
      if (hiddenSet.has(itemId)) hiddenSet.delete(itemId);
      else hiddenSet.add(itemId);
      renderPlayerTables();
      renderCompare();
      try {
        await setHidden(player);
      } catch (err) {
        setStatus(`Failed to persist hidden items: ${err.message}`);
      }
    });
  });
}

function renderCompare() {
  const rows = new Map();
  for (const player of PLAYERS) {
    const model = state.players[player];
    const sourceItems = model.snapshot?.items || [];
    for (const entry of sourceItems) {
      const id = Number(entry.id);
      if (!state.includeHiddenCompare && model.hiddenIds.has(id)) continue;
      if (!rows.has(id)) rows.set(id, { 'Ad The Saint': 0, 'Sic Saint': 0 });
      rows.get(id)[player] = Number(entry.qty || 0);
    }
  }

  const tbody = document.getElementById('compareBody');
  tbody.innerHTML = [...rows.entries()].sort((a, b) => a[0] - b[0]).map(([id, byPlayer]) => {
    const ad = byPlayer['Ad The Saint'] || 0;
    const sic = byPlayer['Sic Saint'] || 0;
    return `<tr><td>${id}</td><td>${ad}</td><td>${sic}</td><td>${ad - sic}</td></tr>`;
  }).join('');
}

async function refreshAndRender() {
  await fetchRemoteState();
  renderPlayerTables();
  renderCompare();
}

function bindUi() {
  const apiInput = document.getElementById('apiUrl');
  const secretInput = document.getElementById('writeSecret');
  apiInput.value = state.apiUrl;
  secretInput.value = state.writeSecret;

  apiInput.addEventListener('change', () => {
    state.apiUrl = apiInput.value.trim();
    localStorage.setItem('apiUrl', state.apiUrl);
  });

  secretInput.addEventListener('change', () => {
    state.writeSecret = secretInput.value;
    localStorage.setItem('writeSecret', state.writeSecret);
  });

  document.getElementById('showHiddenToggle').addEventListener('change', (event) => {
    state.showHidden = event.target.checked;
    renderPlayerTables();
  });

  document.getElementById('includeHiddenCompareToggle').addEventListener('change', (event) => {
    state.includeHiddenCompare = event.target.checked;
    renderCompare();
  });

  document.getElementById('testConnectionBtn').addEventListener('click', async () => {
    try {
      await refreshAndRender();
      setStatus('Connection successful. Data refreshed from server.');
    } catch (err) {
      setStatus(`Connection failed: ${err.message}`);
    }
  });
}

bindUi();
if (state.apiUrl) {
  refreshAndRender().catch((err) => setStatus(`Initial load failed: ${err.message}`));
}
