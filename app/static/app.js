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
  return unit === 'hours' ? `0 */${n} * * *` : `*/${n} * * * *`;
}

function cronToHuman(cron) {
  if (!cron) return '';
  const hourly = cron.match(/^0 \*\/(\d+) \* \* \*$/);
  const minutely = cron.match(/^\*\/(\d+) \* \* \* \*$/);
  if (cron === '0 * * * *') return 'Runs every hour';
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
  const res = await fetch('/api/config');
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
}

document.getElementById('settings-form').addEventListener('submit', async e => {
  e.preventDefault();
  const form = e.target;
  const errorEl = document.getElementById('settings-error');
  errorEl.classList.add('hidden');

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
  es.onmessage = ev => {
    if (ev.data === '__DONE__') {
      es.close();
      btn.disabled = false;
      loadSyncStatus();
      return;
    }
    log.textContent += ev.data + '\n';
    log.scrollTop = log.scrollHeight;
  };
  es.onerror = () => {
    es.close();
    btn.disabled = false;
  };
});

// ── Recordings tab ────────────────────────────────────────────────────────
async function loadRecordings() {
  const container = document.getElementById('recordings-tree');
  container.innerHTML = '<p class="muted">Loading...</p>';
  const res = await fetch('/api/recordings');
  const sessions = await res.json();

  if (!Array.isArray(sessions) || sessions.length === 0) {
    container.innerHTML = '<p class="muted">No recordings found. Run a sync to pull recordings from your device.</p>';
    return;
  }

  container.innerHTML = sessions.map(session => `
    <details class="session">
      <summary>${session.session}</summary>
      ${session.segments.map(seg => `
        <div class="segment">
          <div class="segment-label">Segment ${seg.segment}</div>
          ${seg.files.includes('qcamera.ts') ? `
            <video controls preload="metadata"
              src="/files/realdata/${encodeURIComponent(session.session)}/${seg.segment}/qcamera.ts">
            </video>
          ` : ''}
          <div class="downloads">
            ${seg.files.map(f => `
              <a href="/files/realdata/${encodeURIComponent(session.session)}/${seg.segment}/${encodeURIComponent(f)}"
                 download="${f}">${f}</a>
            `).join('')}
          </div>
        </div>
      `).join('')}
    </details>
  `).join('');
}

// ── Init ──────────────────────────────────────────────────────────────────
loadConfig();
loadSyncStatus();
loadRecordings();
