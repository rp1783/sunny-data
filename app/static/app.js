// ── Tab switching ──────────────────────────────────────────────────────────
document.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
    document.querySelectorAll('.tab-panel').forEach(p => p.classList.add('hidden'));
    btn.classList.add('active');
    document.getElementById(`tab-${btn.dataset.tab}`).classList.remove('hidden');
    if (btn.dataset.tab === 'recordings') loadRecordings();
    if (btn.dataset.tab === 'sync') loadSyncStatus();
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

// ── Recordings tab ────────────────────────────────────────────────────────
let _openSessionEl = null;

function _fileColor(filename) {
  if (filename.endsWith('.ts'))   return '#86efac';
  if (filename.endsWith('.hevc')) return '#93c5fd';
  return '#9ca3af';
}

function _renderSegment(seg, hasStitched) {
  const safePath = escHtml(seg.path);
  const downloads = seg.files.map(f => `
    <a class="dl-pill" style="color:${_fileColor(f)};border-color:${_fileColor(f)}"
       href="/files/${safePath}/${encodeURIComponent(f)}" download="${escHtml(f)}">
      ⬇ ${escHtml(f)}
    </a>
  `).join('');
  return `
    <div class="seg-card">
      <div class="seg-header">Segment ${seg.index + 1} · ${escHtml(seg.time_label)}</div>
      <div class="dl-row">${downloads}</div>
    </div>
  `;
}

function _renderSession(session) {
  const stitchedVideo = session.stitched_path ? `
    <video controls preload="metadata" class="session-video"
      src="/files/${escHtml(session.stitched_path)}"></video>
  ` : '';
  const segsHtml = session.segments.map(seg => _renderSegment(seg, !!session.stitched_path)).join('');
  const segCount = session.segments.length;
  const meta = `${escHtml(session.start_label)} · ${session.duration_min} min · ${segCount} segment${segCount === 1 ? '' : 's'}`;
  return `
    <div class="session-card" data-session="${escHtml(session.session)}">
      <div class="session-header">
        <span class="session-chevron">▶</span>
        <span class="session-meta">${meta}</span>
      </div>
      <div class="session-body hidden">
        ${stitchedVideo}
        ${segsHtml}
      </div>
    </div>
  `;
}

function _renderDateGroup(group) {
  const sessionsHtml = group.sessions.map(_renderSession).join('');
  return `
    <div class="date-group">
      <div class="date-header">${escHtml(group.date_label)}</div>
      ${sessionsHtml}
    </div>
  `;
}

function _attachSessionToggles(container) {
  container.querySelectorAll('.session-header').forEach(header => {
    header.addEventListener('click', () => {
      const card = header.closest('.session-card');
      const body = card.querySelector('.session-body');
      const chevron = card.querySelector('.session-chevron');
      const isOpen = !body.classList.contains('hidden');

      // Collapse previously open session
      if (_openSessionEl && _openSessionEl !== card) {
        _openSessionEl.querySelector('.session-body').classList.add('hidden');
        _openSessionEl.querySelector('.session-chevron').textContent = '▶';
      }

      if (isOpen) {
        body.classList.add('hidden');
        chevron.textContent = '▶';
        _openSessionEl = null;
      } else {
        body.classList.remove('hidden');
        chevron.textContent = '▼';
        _openSessionEl = card;
      }
    });
  });
}

async function loadRecordings() {
  _openSessionEl = null;
  const container = document.getElementById('recordings-tree');
  container.innerHTML = '<p class="muted">Loading...</p>';
  try {
    const res = await fetch('/api/recordings');
    if (!res.ok) {
      container.innerHTML = '<p class="error">Failed to load recordings.</p>';
      return;
    }
    const groups = await res.json();
    if (!Array.isArray(groups) || groups.length === 0) {
      container.innerHTML = '<p class="muted">No recordings yet — run a sync to pull from your device.</p>';
      return;
    }
    container.innerHTML = groups.map(_renderDateGroup).join('');
    _attachSessionToggles(container);
  } catch {
    container.innerHTML = '<p class="error">Error loading recordings.</p>';
  }
}

// ── Stitch ────────────────────────────────────────────────────────────────
document.getElementById('stitch-all-btn').addEventListener('click', async () => {
  const btn = document.getElementById('stitch-all-btn');
  const status = document.getElementById('stitch-status');
  btn.disabled = true;
  status.textContent = 'Stitching in background — reload recordings in a moment...';
  status.classList.remove('hidden');

  await fetch('/api/stitch', {method: 'POST'});

  setTimeout(() => {
    loadRecordings();
    btn.disabled = false;
    status.classList.add('hidden');
  }, 5000);
});

// ── Init ──────────────────────────────────────────────────────────────────
loadConfig();
loadSyncStatus();
loadRecordings();
