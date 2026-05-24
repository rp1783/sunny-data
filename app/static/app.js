// ── Tab switching ──────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
    btn.classList.add('active');
    document.getElementById(`tab-${btn.dataset.tab}`).classList.remove('hidden');
    if (btn.dataset.tab === 'recordings') loadRecordings();
    if (btn.dataset.tab === 'sync') loadSyncStatus();
    if (btn.dataset.tab === 'logs') startLogPolling();
  });
});

// ── HTML escaping ─────────────────────────────────────────────────────────
function escHtml(s) {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

// ── Banner ────────────────────────────────────────────────────────────────
function showBanner(msg) {
  const el = document.getElementById('banner');
  el.textContent = msg;
  el.classList.remove('hidden');
}
function hideBanner() {
  document.getElementById('banner').classList.add('hidden');
}

// ── Config load/save ──────────────────────────────────────────────────────
async function loadConfig() {
  try {
    const res = await fetch('/api/config');
    if (!res.ok) { showBanner('Configuration incomplete — go to Settings to set up.'); return; }
    const cfg = await res.json();
    if (!cfg || Object.keys(cfg).length === 0) {
      showBanner('Configuration incomplete — go to Settings to set up.');
      return;
    }
    hideBanner();
    const form = document.getElementById('settings-form');
    ['device_ip', 'device_user', 'ssh_port', 'remote_path', 'local_path'].forEach(k => {
      const el = form.elements[k];
      if (el && cfg[k] != null) el.value = cfg[k];
    });
    if (cfg.ssh_key_set) {
      document.querySelector('[name="ssh_key"]').placeholder =
        'SSH key is set. Paste a new key here only if you want to replace it.';
    }
  } catch {
    showBanner('Could not load configuration — is the server running?');
  }
}

document.getElementById('settings-form').addEventListener('submit', async e => {
  e.preventDefault();
  const form = e.target;
  const errorEl = document.getElementById('settings-error');
  errorEl.classList.add('hidden');
  errorEl.style.color = '';

  const sshKey = form.elements['ssh_key'].value.trim();
  if (sshKey) {
    const kr = await fetch('/api/ssh-key', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({key: sshKey}),
    });
    if (!kr.ok) {
      const err = await kr.json().catch(() => ({}));
      errorEl.textContent = err.detail || 'Failed to save SSH key';
      errorEl.classList.remove('hidden');
      return;
    }
    form.elements['ssh_key'].value = '';
  }

  const payload = {
    device_ip: form.elements['device_ip'].value.trim(),
    device_user: form.elements['device_user'].value.trim(),
    ssh_port: parseInt(form.elements['ssh_port'].value, 10),
    remote_path: form.elements['remote_path'].value.trim(),
    local_path: form.elements['local_path'].value.trim(),
  };

  const res = await fetch('/api/config', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    errorEl.textContent = err.detail || 'Failed to save settings';
    errorEl.classList.remove('hidden');
    return;
  }

  hideBanner();
  errorEl.textContent = 'Settings saved.';
  errorEl.style.color = '#86efac';
  errorEl.classList.remove('hidden');
  setTimeout(() => errorEl.classList.add('hidden'), 2500);
});

// ── Sync tab ──────────────────────────────────────────────────────────────
async function loadSyncStatus() {
  const res = await fetch('/api/sync/status');
  const data = await res.json();
  const label = document.getElementById('last-sync-label');
  const badge = document.getElementById('sync-badge');
  if (data.last_sync && data.last_sync.timestamp) {
    label.textContent = `Last sync: ${new Date(data.last_sync.timestamp).toLocaleString()}`;
    badge.textContent = data.last_sync.status;
    badge.className = `badge badge-${data.last_sync.status}`;
  }
}

document.getElementById('pull-now-btn').addEventListener('click', async () => {
  const btn = document.getElementById('pull-now-btn');
  const log = document.getElementById('sync-log');
  btn.disabled = true;
  log.textContent = '';

  const res = await fetch('/api/sync/run', {method: 'POST'});
  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    log.textContent = err.detail || 'Failed to start sync';
    btn.disabled = false;
    return;
  }

  const es = new EventSource('/api/sync/stream');
  const esTimeout = setTimeout(() => { es.close(); btn.disabled = false; }, 5 * 60 * 1000);
  es.onmessage = ev => {
    if (ev.data === '__DONE__') {
      clearTimeout(esTimeout);
      es.close();
      btn.disabled = false;
      loadSyncStatus();
      loadRecordings();
      return;
    }
    log.textContent += ev.data + '\n';
    log.scrollTop = log.scrollHeight;
  };
  es.onerror = () => {
    clearTimeout(esTimeout);
    es.close();
    btn.disabled = false;
  };
});

// ── Log tab ───────────────────────────────────────────────────────────────
let _logPollTimer = null;
let _logEntries = [];

const _levelColor = {
  ERROR:   '#f87171',
  WARNING: '#fbbf24',
  INFO:    '#6b7280',
  SYNC:    '#93c5fd',
};

function _renderLogs() {
  const list = document.getElementById('log-list');
  if (_logEntries.length === 0) {
    list.innerHTML = '<p class="muted log-empty">No log entries yet.</p>';
    return;
  }
  list.innerHTML = _logEntries.map(e => `
    <div class="log-entry">
      <span class="log-ts">${escHtml(e.ts)}</span>
      <span class="log-level" style="color:${_levelColor[e.level] || '#9ca3af'}">${escHtml(e.level)}</span>
      <span class="log-msg">${escHtml(e.msg)}</span>
    </div>
  `).join('');
  const autoScroll = document.getElementById('log-autoscroll').checked;
  if (autoScroll) list.scrollTop = list.scrollHeight;
}

async function _pollLogs() {
  try {
    const res = await fetch('/api/logs');
    if (res.ok) {
      _logEntries = await res.json();
      _renderLogs();
    }
  } catch {}
}

function startLogPolling() {
  _pollLogs();
  if (!_logPollTimer) {
    _logPollTimer = setInterval(_pollLogs, 5000);
  }
}

document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    if (btn.dataset.tab !== 'logs' && _logPollTimer) {
      clearInterval(_logPollTimer);
      _logPollTimer = null;
    }
  });
});

document.getElementById('log-clear-btn').addEventListener('click', () => {
  _logEntries = [];
  _renderLogs();
});

// ── Stats helpers ─────────────────────────────────────────────────────────
function _fmtCardStats(stats) {
  if (!stats) return '';
  const parts = [];
  if (stats.distance_miles != null) parts.push(`<span class="stat-val">${stats.distance_miles.toFixed(1)}</span> mi`);
  if (stats.avg_speed_mph != null)  parts.push(`avg <span class="stat-val">${Math.round(stats.avg_speed_mph)}</span> mph`);
  if (stats.openpilot_active_min != null) parts.push(`OP <span class="stat-val">${stats.openpilot_active_min.toFixed(0)}</span>m`);
  return parts.join(' · ');
}

function _statTile(label, value, unit, index) {
  return `
    <div class="stat-tile" style="--i:${index}">
      <div class="stat-tile-label">${escHtml(label)}</div>
      <div class="stat-tile-value">${escHtml(String(value))}${unit ? `<span class="stat-tile-unit">${escHtml(unit)}</span>` : ''}</div>
    </div>`;
}

function _renderStatsGrid(stats) {
  if (!stats) return '';
  const tiles = [
    _statTile('Distance', stats.distance_miles != null ? stats.distance_miles.toFixed(1) : '—', 'mi', 0),
    _statTile('Avg Speed', stats.avg_speed_mph != null ? Math.round(stats.avg_speed_mph) : '—', 'mph', 1),
    _statTile('Max Speed', stats.max_speed_mph != null ? Math.round(stats.max_speed_mph) : '—', 'mph', 2),
    _statTile('OP Active', stats.openpilot_active_min != null ? stats.openpilot_active_min.toFixed(1) : '—', 'min', 3),
    _statTile('Disengaged', stats.disengagements != null ? stats.disengagements : '—', '', 4),
  ].join('');
  return `<div class="stats-grid">${tiles}</div>`;
}

// ── Recordings: helpers ───────────────────────────────────────────────────
let _sessionsMap = new Map();

function _fileColor(filename) {
  if (filename.endsWith('.ts'))   return '#86efac';
  if (filename.endsWith('.hevc')) return '#93c5fd';
  return '#9ca3af';
}

// ── Recordings: YouTube grid ──────────────────────────────────────────────
function _renderCard(session) {
  _sessionsMap.set(session.session, session);
  const thumb = session.thumbnail_path
    ? `<img class="rec-thumb-img" src="/files/${escHtml(session.thumbnail_path)}" loading="lazy" alt="">`
    : `<div class="rec-thumb-placeholder">▶</div>`;

  return `
    <div class="rec-card" data-sid="${escHtml(session.session)}">
      <div class="rec-thumb-wrap">
        ${thumb}
        <span class="rec-duration">${session.duration_min} min</span>
        <button class="star-btn${session.starred ? ' starred' : ''}" data-sid="${escHtml(session.session)}" title="${session.starred ? 'Unstar' : 'Star to protect from deletion'}">
          ${session.starred ? '★' : '☆'}
        </button>
      </div>
      <div class="rec-info">
        <div class="rec-title">${escHtml(session.start_label)}</div>
        ${session.stats ? `<div class="rec-stats">${_fmtCardStats(session.stats)}</div>` : ''}
      </div>
    </div>
  `;
}

function _renderDateGroup(group) {
  const cards = group.sessions.map(_renderCard).join('');
  return `
    <div class="date-group">
      <div class="date-header">${escHtml(group.date_label)}</div>
      <div class="recordings-grid">${cards}</div>
    </div>
  `;
}

let _allGroups = [];

function _renderRecordings() {
  const filter = document.getElementById('date-filter').value;
  const root = document.getElementById('recordings-grid-root');
  const visible = filter ? _allGroups.filter(g => g.date === filter) : _allGroups;
  if (visible.length === 0) {
    root.innerHTML = '<p class="muted">No recordings for this date.</p>';
    return;
  }
  _sessionsMap.clear();
  root.innerHTML = visible.map(_renderDateGroup).join('');
  root.querySelectorAll('.rec-card').forEach(card => {
    card.addEventListener('click', () => {
      const session = _sessionsMap.get(card.dataset.sid);
      if (session) openModal(session);
    });
  });
  root.querySelectorAll('.star-btn').forEach(btn => {
    btn.addEventListener('click', async e => {
      e.stopPropagation();
      const sid = btn.dataset.sid;
      const session = _sessionsMap.get(sid);
      if (!session) return;
      const nowStarred = !session.starred;
      await fetch(`/api/star/${encodeURIComponent(sid)}`, {
        method: nowStarred ? 'POST' : 'DELETE',
      });
      session.starred = nowStarred;
      btn.textContent = nowStarred ? '★' : '☆';
      btn.classList.toggle('starred', nowStarred);
      btn.title = nowStarred ? 'Unstar' : 'Star to protect from deletion';
    });
  });
}

async function loadRecordings() {
  const root = document.getElementById('recordings-grid-root');
  root.innerHTML = '<p class="muted">Loading...</p>';
  try {
    const res = await fetch('/api/recordings');
    if (!res.ok) { root.innerHTML = '<p class="error">Failed to load recordings.</p>'; return; }
    const groups = await res.json();
    if (!Array.isArray(groups) || groups.length === 0) {
      root.innerHTML = '<p class="muted">No recordings yet — run a sync to pull from your device.</p>';
      return;
    }
    _allGroups = groups;
    const sel = document.getElementById('date-filter');
    const prev = sel.value;
    sel.innerHTML = '<option value="">All dates</option>' +
      groups.map(g => `<option value="${escHtml(g.date)}">${escHtml(g.date_label)}</option>`).join('');
    if (prev && groups.some(g => g.date === prev)) sel.value = prev;
    _renderRecordings();
  } catch {
    root.innerHTML = '<p class="error">Error loading recordings.</p>';
  }
}

document.getElementById('date-filter').addEventListener('change', () => {
  const hasValue = !!document.getElementById('date-filter').value;
  document.getElementById('date-filter-clear').classList.toggle('hidden', !hasValue);
  _renderRecordings();
});

document.getElementById('date-filter-clear').addEventListener('click', () => {
  document.getElementById('date-filter').value = '';
  document.getElementById('date-filter-clear').classList.add('hidden');
  _renderRecordings();
});

// ── Modal ─────────────────────────────────────────────────────────────────
let _leafletMap = null;

function openModal(session) {
  const video = session.stitched_path ? `
    <video controls autoplay class="modal-video"
      src="/files/${escHtml(session.stitched_path)}"></video>
  ` : '<p class="muted modal-no-video">No stitched video — click Stitch All Sessions to generate one.</p>';

  const downloads = (session.downloads || []).map(d => {
    const fname = d.path.split('/').pop();
    return `<a class="dl-pill" style="color:#f59e0b;border-color:rgba(245,158,11,0.4)"
       href="/files/${escHtml(d.path)}" download="${escHtml(fname)}">
      ⬇ ${escHtml(d.label)}
    </a>`;
  }).join('');

  const stats = session.stats;
  const hasRoute = stats && stats.route_points && stats.route_points.length > 1;
  const mapHtml = hasRoute ? '<div id="route-map"></div>' : '';

  document.getElementById('modal-content').innerHTML = `
    ${video}
    <div class="modal-title">${escHtml(session.start_label)} · ${session.duration_min} min · ${session.segments.length} segment${session.segments.length === 1 ? '' : 's'}</div>
    ${_renderStatsGrid(stats)}
    ${mapHtml}
    ${downloads ? `<div class="modal-downloads"><div class="modal-section-label">Downloads</div><div class="dl-row">${downloads}</div></div>` : ''}
  `;

  document.getElementById('rec-modal').classList.remove('hidden');
  document.body.style.overflow = 'hidden';

  if (hasRoute) {
    requestAnimationFrame(() => _initRouteMap(stats.route_points, stats.gps_start, stats.gps_end));
  }
}

async function _reverseGeocode(lat, lon) {
  try {
    const res = await fetch(
      `https://nominatim.openstreetmap.org/reverse?format=jsonv2&lat=${lat}&lon=${lon}&zoom=16`,
      { headers: { 'Accept-Language': 'en' } }
    );
    if (!res.ok) return null;
    const data = await res.json();
    const a = data.address || {};
    return [a.road, a.suburb || a.neighbourhood || a.city_district, a.city || a.town || a.village]
      .filter(Boolean).join(', ') || data.display_name?.split(',').slice(0, 2).join(',').trim() || null;
  } catch { return null; }
}

function _makeMarkerPopup(marker, label, cssClass, latLon) {
  const placeholder = `<div class="map-popup-label ${cssClass}">${label}</div><div class="map-popup-addr">Looking up…</div>`;
  const popup = L.popup({ offset: [0, -4], autoPan: false }).setContent(placeholder);
  marker.bindPopup(popup);

  let fetched = false;
  marker.on('mouseover', function() {
    this.openPopup();
    if (fetched) return;
    fetched = true;
    _reverseGeocode(latLon[0], latLon[1]).then(addr => {
      popup.setContent(
        `<div class="map-popup-label ${cssClass}">${label}</div>` +
        `<div class="map-popup-addr">${addr || 'Address unavailable'}</div>`
      );
    });
  });
  marker.on('mouseout', function() { this.closePopup(); });
}

function _initRouteMap(points, gpsStart, gpsEnd) {
  if (typeof L === 'undefined') return;
  if (_leafletMap) { _leafletMap.remove(); _leafletMap = null; }
  const mapEl = document.getElementById('route-map');
  if (!mapEl) return;
  _leafletMap = L.map(mapEl, { zoomControl: true, attributionControl: false });
  L.tileLayer('https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png', {
    maxZoom: 19,
    subdomains: 'abcd',
  }).addTo(_leafletMap);

  const line = L.polyline(points, { color: '#f59e0b', weight: 2.5, opacity: 0.85 }).addTo(_leafletMap);
  _leafletMap.fitBounds(line.getBounds(), { padding: [20, 20] });

  const dotStyle = { radius: 6, weight: 1.5, opacity: 1, fillOpacity: 0.9 };
  if (gpsStart) {
    const m = L.circleMarker(gpsStart, { ...dotStyle, color: '#16a34a', fillColor: '#22c55e' }).addTo(_leafletMap);
    _makeMarkerPopup(m, 'Start', 'start', gpsStart);
  }
  if (gpsEnd) {
    const m = L.circleMarker(gpsEnd, { ...dotStyle, color: '#b91c1c', fillColor: '#ef4444' }).addTo(_leafletMap);
    _makeMarkerPopup(m, 'End', 'end', gpsEnd);
  }
}

function closeModal() {
  const modal = document.getElementById('rec-modal');
  modal.classList.add('hidden');
  document.body.style.overflow = '';
  const video = modal.querySelector('video');
  if (video) { video.pause(); video.src = ''; }
  if (_leafletMap) { _leafletMap.remove(); _leafletMap = null; }
}

document.getElementById('modal-close').addEventListener('click', closeModal);
document.getElementById('rec-modal').addEventListener('click', e => {
  if (e.target === document.getElementById('rec-modal')) closeModal();
});
document.addEventListener('keydown', e => {
  if (e.key === 'Escape') closeModal();
});

// ── Init ──────────────────────────────────────────────────────────────────
loadConfig();
loadSyncStatus();
loadRecordings();
