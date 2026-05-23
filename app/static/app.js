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

// ── Schedule helpers ──────────────────────────────────────────────────────
function simpleToCron() {
  const n = parseInt(document.getElementById('interval-value').value, 10) || 1;
  const unit = document.getElementById('interval-unit').value;
  if (unit === 'hours') {
    return n >= 24 ? '0 0 * * *' : (n === 1 ? '0 * * * *' : `0 */${n} * * *`);
  }
  return n === 1 ? '* * * * *' : `*/${n} * * * *`;
}

function cronToHuman(cron) {
  if (!cron) return '';
  const hourly = cron.match(/^0 \*\/(\d+) \* \* \*$/);
  const minutely = cron.match(/^\*\/(\d+) \* \* \* \*$/);
  if (cron === '0 * * * *') return 'Runs every hour';
  if (cron === '* * * * *') return 'Runs every minute';
  if (cron === '0 0 * * *') return 'Runs every 24 hours (daily at midnight)';
  if (hourly) return `Runs every ${hourly[1]} hour(s)`;
  if (minutely) return `Runs every ${minutely[1]} minute(s)`;
  return `Schedule: ${cron}`;
}

function updateCronPreview(cron) {
  document.getElementById('cron-preview').textContent = cronToHuman(cron);
}

function syncScheduleInputFromSimple() {
  const cron = simpleToCron();
  document.querySelector('[name="schedule"]').value = cron;
  updateCronPreview(cron);
}

function applyScheduleToForm(schedule) {
  const scheduleInput = document.querySelector('[name="schedule"]');
  scheduleInput.value = schedule;
  updateCronPreview(schedule);

  const hourly = schedule.match(/^0 \*\/(\d+) \* \* \*$/);
  const minutely = schedule.match(/^\*\/(\d+) \* \* \* \*$/);
  if (schedule === '0 * * * *') {
    document.getElementById('interval-value').value = 1;
    document.getElementById('interval-unit').value = 'hours';
  } else if (schedule === '0 0 * * *') {
    document.getElementById('interval-value').value = 24;
    document.getElementById('interval-unit').value = 'hours';
  } else if (hourly) {
    document.getElementById('interval-value').value = hourly[1];
    document.getElementById('interval-unit').value = 'hours';
  } else if (minutely) {
    document.getElementById('interval-value').value = minutely[1];
    document.getElementById('interval-unit').value = 'minutes';
  } else {
    document.getElementById('schedule-advanced').classList.remove('hidden');
    document.getElementById('toggle-advanced').textContent = 'Simple ▴';
  }
}

document.getElementById('interval-value').addEventListener('input', syncScheduleInputFromSimple);
document.getElementById('interval-unit').addEventListener('change', syncScheduleInputFromSimple);

document.querySelector('[name="schedule"]').addEventListener('input', e => {
  updateCronPreview(e.target.value);
});

document.getElementById('toggle-advanced').addEventListener('click', () => {
  const adv = document.getElementById('schedule-advanced');
  const open = adv.classList.toggle('hidden');
  document.getElementById('toggle-advanced').textContent = open ? 'Advanced ▾' : 'Simple ▴';
  if (!open) {
    // Switching to advanced: ensure input reflects current simple value
    syncScheduleInputFromSimple();
  }
});

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
    if (cfg.schedule) applyScheduleToForm(cfg.schedule);
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

  const advOpen = !document.getElementById('schedule-advanced').classList.contains('hidden');
  const schedule = advOpen
    ? (form.elements['schedule'].value.trim() || simpleToCron())
    : simpleToCron();

  const payload = {
    device_ip: form.elements['device_ip'].value.trim(),
    device_user: form.elements['device_user'].value.trim(),
    ssh_port: parseInt(form.elements['ssh_port'].value, 10),
    remote_path: form.elements['remote_path'].value.trim(),
    local_path: form.elements['local_path'].value.trim(),
    schedule,
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

function _renderSegment(seg) {
  const safePath = escHtml(seg.path);
  const videoHtml = seg.files.includes('qcamera.ts') ? `
    <video controls preload="metadata" class="seg-video"
      src="/files/${safePath}/qcamera.ts"></video>
  ` : '';
  const downloads = seg.files.map(f => `
    <a class="dl-pill" style="color:${_fileColor(f)};border-color:${_fileColor(f)}"
       href="/files/${safePath}/${encodeURIComponent(f)}" download="${escHtml(f)}">
      ⬇ ${escHtml(f)}
    </a>
  `).join('');
  return `
    <div class="seg-card">
      <div class="seg-header">Segment ${seg.index + 1} · ${escHtml(seg.time_label)}</div>
      ${videoHtml}
      <div class="dl-row">${downloads}</div>
    </div>
  `;
}

function _renderSession(session) {
  const segsHtml = session.segments.map(_renderSegment).join('');
  const meta = `${escHtml(session.start_label)} · ${session.duration_min} min · ${session.segments.length} segment${session.segments.length === 1 ? '' : 's'}`;
  return `
    <div class="session-card" data-session="${escHtml(session.session)}">
      <div class="session-header">
        <span class="session-chevron">▶</span>
        <span class="session-meta">${meta}</span>
      </div>
      <div class="session-body hidden">${segsHtml}</div>
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

// ── Init ──────────────────────────────────────────────────────────────────
loadConfig();
loadSyncStatus();
loadRecordings();
