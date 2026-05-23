# Recordings UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the opaque route-ID recording browser with a date-grouped, human-readable UI showing session start times, durations, inline video previews, and styled download links.

**Architecture:** `build_recording_tree()` is extended to derive timestamps from folder mtimes and return a date-grouped response shape. The frontend `loadRecordings()` function is rewritten to render date headers, collapsible session cards, and segment video+download cards. CSS for the new components is added to `style.css`.

**Tech Stack:** Python 3.12 (`datetime`, `os.path.getmtime`), FastAPI, plain HTML/CSS/JS, pytest

---

## File Map

| File | Change |
|---|---|
| `app/recordings.py` | Rewrite `build_recording_tree()` to return date-grouped shape with timestamps |
| `app/static/app.js` | Rewrite `loadRecordings()` and add session card toggle logic |
| `app/static/style.css` | Add styles for date headers, session cards, segment cards, download pills |
| `tests/test_recordings.py` | Update existing tests to new shape; add timestamp/grouping tests |

---

## Task 1: Update tests for new `build_recording_tree()` return shape

The existing tests assert the old flat shape (`session`, `segments[].segment`). The new shape nests sessions inside date groups. Update all existing tests and add new ones for timestamps and grouping.

**Files:**
- Modify: `tests/test_recordings.py`

- [ ] **Step 1: Replace the entire test file**

```python
import os
import time
from pathlib import Path
from recordings import build_recording_tree, resolve_file_path


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_flat_seg(base: Path, folder: str, files: list[str], mtime: float | None = None) -> Path:
    """Create a flat-layout segment folder (routeId--segN/files)."""
    seg_dir = base / "realdata" / folder
    seg_dir.mkdir(parents=True)
    for f in files:
        (seg_dir / f).write_text("data")
    if mtime is not None:
        os.utime(seg_dir, (mtime, mtime))
    return seg_dir


def _make_nested_seg(base: Path, session: str, segment: str, files: list[str], mtime: float | None = None) -> Path:
    """Create a nested-layout segment folder (session/segN/files)."""
    seg_dir = base / "realdata" / session / segment
    seg_dir.mkdir(parents=True)
    for f in files:
        (seg_dir / f).write_text("data")
    if mtime is not None:
        os.utime(seg_dir, (mtime, mtime))
    return seg_dir


# ── Empty / missing ────────────────────────────────────────────────────────

def test_build_tree_empty_when_no_realdata_dir(tmp_path):
    assert build_recording_tree(str(tmp_path)) == []


def test_build_tree_empty_when_no_dirs(tmp_path):
    (tmp_path / "realdata").mkdir()
    assert build_recording_tree(str(tmp_path)) == []


# ── Flat layout ────────────────────────────────────────────────────────────

def test_flat_single_session_returns_one_date_group(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    _make_flat_seg(tmp_path, "abc--def--0", ["qcamera.ts", "fcamera.hevc"], mtime=t0)
    result = build_recording_tree(str(tmp_path))
    assert len(result) == 1
    assert result[0]["date"] == "2026-05-22"
    assert "May 22" in result[0]["date_label"]
    assert len(result[0]["sessions"]) == 1


def test_flat_session_has_start_label_and_duration(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    t1 = t0 + 60
    _make_flat_seg(tmp_path, "abc--def--0", ["qcamera.ts"], mtime=t0)
    _make_flat_seg(tmp_path, "abc--def--1", ["qcamera.ts"], mtime=t1)
    result = build_recording_tree(str(tmp_path))
    session = result[0]["sessions"][0]
    assert session["duration_min"] == 2
    assert ":" in session["start_label"]   # has time formatting


def test_flat_segment_has_index_and_time_label(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    _make_flat_seg(tmp_path, "abc--def--0", ["qcamera.ts"], mtime=t0)
    _make_flat_seg(tmp_path, "abc--def--1", ["qcamera.ts"], mtime=t0 + 60)
    result = build_recording_tree(str(tmp_path))
    segs = result[0]["sessions"][0]["segments"]
    assert segs[0]["index"] == 0
    assert segs[1]["index"] == 1
    assert "–" in segs[0]["time_label"]


def test_flat_file_ordering_qcamera_first(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    _make_flat_seg(tmp_path, "abc--def--0", ["rlog.zst", "qcamera.ts", "fcamera.hevc"], mtime=t0)
    result = build_recording_tree(str(tmp_path))
    files = result[0]["sessions"][0]["segments"][0]["files"]
    assert files[0] == "qcamera.ts"
    assert files[1:] == sorted(["rlog.zst", "fcamera.hevc"])


def test_flat_segments_sorted_by_index(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    for i in [2, 0, 1]:
        _make_flat_seg(tmp_path, f"abc--def--{i}", ["qcamera.ts"], mtime=t0 + i * 60)
    result = build_recording_tree(str(tmp_path))
    segs = result[0]["sessions"][0]["segments"]
    assert [s["index"] for s in segs] == [0, 1, 2]


def test_flat_skips_empty_segment_folders(tmp_path):
    (tmp_path / "realdata" / "abc--def--0").mkdir(parents=True)
    result = build_recording_tree(str(tmp_path))
    assert result == []


# ── Date grouping ──────────────────────────────────────────────────────────

def test_sessions_on_different_dates_get_separate_groups(tmp_path):
    t_may22 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    t_may23 = time.mktime(time.strptime("2026-05-23 10:00:00", "%Y-%m-%d %H:%M:%S"))
    _make_flat_seg(tmp_path, "aaa--bbb--0", ["qcamera.ts"], mtime=t_may22)
    _make_flat_seg(tmp_path, "ccc--ddd--0", ["qcamera.ts"], mtime=t_may23)
    result = build_recording_tree(str(tmp_path))
    assert len(result) == 2
    dates = [g["date"] for g in result]
    assert "2026-05-23" in dates
    assert "2026-05-22" in dates
    # Newest date first
    assert result[0]["date"] == "2026-05-23"


def test_sessions_within_date_sorted_newest_first(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    t1 = time.mktime(time.strptime("2026-05-22 20:00:00", "%Y-%m-%d %H:%M:%S"))
    _make_flat_seg(tmp_path, "aaa--bbb--0", ["qcamera.ts"], mtime=t0)
    _make_flat_seg(tmp_path, "ccc--ddd--0", ["qcamera.ts"], mtime=t1)
    result = build_recording_tree(str(tmp_path))
    sessions = result[0]["sessions"]
    assert sessions[0]["start_label"] != sessions[1]["start_label"]
    # The later session (t1 = 20:00) should be first
    assert sessions[0]["session"] == "ccc--ddd"


# ── Nested layout (legacy) ─────────────────────────────────────────────────

def test_nested_single_session_returns_date_group(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    _make_nested_seg(tmp_path, "2024-11-15--08-32-10", "0", ["qcamera.ts", "fcamera.hevc"], mtime=t0)
    result = build_recording_tree(str(tmp_path))
    assert len(result) == 1
    assert result[0]["date"] == "2026-05-22"
    session = result[0]["sessions"][0]
    assert session["session"] == "2024-11-15--08-32-10"
    assert session["duration_min"] == 1


def test_nested_multiple_segments_sorted(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    for i, seg in enumerate(["2", "0", "1"]):
        _make_nested_seg(tmp_path, "2024-11-15--08-32-10", seg, ["qcamera.ts"], mtime=t0 + int(seg) * 60)
    result = build_recording_tree(str(tmp_path))
    segs = result[0]["sessions"][0]["segments"]
    assert [s["index"] for s in segs] == [0, 1, 2]


def test_nested_skips_empty_segments(tmp_path):
    (tmp_path / "realdata" / "2024-11-15--08-32-10" / "0").mkdir(parents=True)
    result = build_recording_tree(str(tmp_path))
    assert result == []


# ── resolve_file_path (unchanged) ─────────────────────────────────────────

def test_resolve_file_path_valid(tmp_path):
    f = tmp_path / "realdata" / "sess" / "0" / "qcamera.ts"
    f.parent.mkdir(parents=True)
    f.write_text("data")
    result = resolve_file_path(str(tmp_path), "realdata/sess/0/qcamera.ts")
    assert result == f


def test_resolve_file_path_blocks_traversal(tmp_path):
    assert resolve_file_path(str(tmp_path), "../etc/passwd") is None


def test_resolve_file_path_returns_none_for_missing_file(tmp_path):
    assert resolve_file_path(str(tmp_path), "realdata/nonexistent.ts") is None
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd /home/ryan/claude/sunny-data && pytest tests/test_recordings.py -v 2>&1 | tail -30
```

Expected: multiple failures (old shape assertions, missing fields).

---

## Task 2: Rewrite `build_recording_tree()` to return the new shape

**Files:**
- Modify: `app/recordings.py`

- [ ] **Step 1: Replace `app/recordings.py`**

```python
import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%-I:%M %p")


def _fmt_time_range(dt: datetime) -> str:
    end = dt + timedelta(minutes=1)
    return f"{_fmt_time(dt)} – {_fmt_time(end)}"


def _fmt_date_label(dt: datetime) -> str:
    return dt.strftime("%A, %B %-d")


def _order_files(files: list[str]) -> list[str]:
    if "qcamera.ts" in files:
        rest = sorted(f for f in files if f != "qcamera.ts")
        return ["qcamera.ts"] + rest
    return sorted(files)


def _group_sessions_by_date(sessions: list[dict]) -> list[dict]:
    """sessions: list of dicts with 'start_dt' (datetime) + all output fields."""
    by_date: dict[str, list] = defaultdict(list)
    for s in sessions:
        date_key = s["start_dt"].strftime("%Y-%m-%d")
        by_date[date_key].append(s)

    result = []
    for date_key in sorted(by_date.keys(), reverse=True):
        day_sessions = sorted(by_date[date_key], key=lambda s: s["start_dt"], reverse=True)
        dt = day_sessions[0]["start_dt"]
        result.append({
            "date": date_key,
            "date_label": _fmt_date_label(dt),
            "sessions": [
                {k: v for k, v in s.items() if k != "start_dt"}
                for s in day_sessions
            ],
        })
    return result


def build_recording_tree(local_path: str) -> list:
    base = Path(local_path).resolve() / "realdata"
    if not base.exists():
        return []

    flat_seg_pattern = re.compile(r"^(.+)--(\d+)$")
    top_dirs = sorted(d for d in base.iterdir() if d.is_dir())

    if not top_dirs:
        return []

    sample = top_dirs[0]
    has_nested = any(sub.is_dir() and sub.name.isdigit() for sub in sample.iterdir())

    if has_nested:
        return _build_nested(base, top_dirs)
    return _build_flat(base, top_dirs, flat_seg_pattern)


def _build_flat(base: Path, top_dirs: list[Path], pattern: re.Pattern) -> list:
    groups: dict[str, list] = defaultdict(list)
    for d in top_dirs:
        m = pattern.match(d.name)
        if m:
            session_name, seg_index = m.group(1), int(m.group(2))
        else:
            session_name, seg_index = d.name, 0
        raw_files = [f.name for f in d.iterdir() if f.is_file()]
        if not raw_files:
            continue
        mtime = os.path.getmtime(d)
        groups[session_name].append((seg_index, d.name, raw_files, mtime))

    sessions = []
    for session_name, segs in groups.items():
        segs_sorted = sorted(segs, key=lambda t: t[0])
        # Start time from the --0 segment's mtime
        start_mtime = next((t[3] for t in segs_sorted if t[0] == 0), segs_sorted[0][3])
        start_dt = datetime.fromtimestamp(start_mtime)
        segments = []
        for seg_index, folder_name, raw_files, _ in segs_sorted:
            seg_dt = start_dt + timedelta(minutes=seg_index)
            segments.append({
                "path": f"realdata/{folder_name}",
                "index": seg_index,
                "time_label": _fmt_time_range(seg_dt),
                "files": _order_files(raw_files),
            })
        sessions.append({
            "session": session_name,
            "start_label": _fmt_time(start_dt),
            "duration_min": len(segments),
            "segments": segments,
            "start_dt": start_dt,
        })

    return _group_sessions_by_date(sessions)


def _build_nested(base: Path, top_dirs: list[Path]) -> list:
    sessions = []
    for session_dir in top_dirs:
        seg_dirs = sorted(
            (d for d in session_dir.iterdir() if d.is_dir() and d.name.isdigit()),
            key=lambda p: int(p.name),
        )
        raw_segments = []
        for seg_dir in seg_dirs:
            raw_files = [f.name for f in seg_dir.iterdir() if f.is_file()]
            if raw_files:
                raw_segments.append((int(seg_dir.name), seg_dir, raw_files))
        if not raw_segments:
            continue

        first_seg_dir = raw_segments[0][1]
        start_dt = datetime.fromtimestamp(os.path.getmtime(first_seg_dir))
        segments = []
        for seg_index, seg_dir, raw_files in raw_segments:
            seg_dt = start_dt + timedelta(minutes=seg_index)
            segments.append({
                "path": f"realdata/{session_dir.name}/{seg_dir.name}",
                "index": seg_index,
                "time_label": _fmt_time_range(seg_dt),
                "files": _order_files(raw_files),
            })
        sessions.append({
            "session": session_dir.name,
            "start_label": _fmt_time(start_dt),
            "duration_min": len(segments),
            "segments": segments,
            "start_dt": start_dt,
        })

    return _group_sessions_by_date(sessions)


def resolve_file_path(local_path: str, rel_path: str) -> Path | None:
    base = Path(local_path).resolve()
    target = (base / rel_path).resolve()
    if not str(target).startswith(str(base) + "/") and target != base:
        return None
    if not target.is_file():
        return None
    return target
```

- [ ] **Step 2: Run tests**

```bash
cd /home/ryan/claude/sunny-data && pytest tests/test_recordings.py -v 2>&1 | tail -30
```

Expected: all pass.

- [ ] **Step 3: Run full test suite to check for regressions**

```bash
cd /home/ryan/claude/sunny-data && pytest tests/ -v 2>&1 | tail -20
```

Expected: all pass. The API test `test_get_recordings_*` (if any) may need updating — check output.

- [ ] **Step 4: Commit**

```bash
cd /home/ryan/claude/sunny-data
git add app/recordings.py tests/test_recordings.py
git commit -m "feat: recordings tree returns date-grouped sessions with timestamps"
```

---

## Task 3: Rewrite `loadRecordings()` in `app.js`

**Files:**
- Modify: `app/static/app.js`

- [ ] **Step 1: Replace the `loadRecordings` function and add session toggle logic**

Find the existing `loadRecordings` function (starts around line 229) and replace everything from `async function loadRecordings()` through the closing `}` with:

```javascript
// ── Recordings tab ────────────────────────────────────────────────────────
let _openSessionEl = null;

function _fileColor(filename) {
  if (filename.endsWith('.ts'))   return '#86efac';
  if (filename.endsWith('.hevc')) return '#93c5fd';
  return '#9ca3af';
}

function _renderSegment(seg) {
  const videoHtml = seg.files.includes('qcamera.ts') ? `
    <video controls preload="metadata" class="seg-video"
      src="/files/${seg.path}/qcamera.ts"></video>
  ` : '';
  const downloads = seg.files.map(f => `
    <a class="dl-pill" style="color:${_fileColor(f)};border-color:${_fileColor(f)}"
       href="/files/${seg.path}/${encodeURIComponent(f)}" download="${escHtml(f)}">
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
```

- [ ] **Step 2: Commit**

```bash
cd /home/ryan/claude/sunny-data
git add app/static/app.js
git commit -m "feat: rewrite recordings UI with date groups and session cards"
```

---

## Task 4: Add CSS for new recording components

**Files:**
- Modify: `app/static/style.css`

- [ ] **Step 1: Append new styles to `style.css`**

Add at the end of `app/static/style.css`:

```css
/* ── Recordings UI ─────────────────────────────────────────────────────── */

.date-group {
  margin-bottom: 24px;
}

.date-header {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #6b7280;
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.date-header::before,
.date-header::after {
  content: '';
  flex: 1;
  height: 1px;
  background: #2a2d3a;
}

.session-card {
  background: #1a1d27;
  border-left: 3px solid #3b82f6;
  border-radius: 8px;
  margin-bottom: 8px;
  overflow: hidden;
}

.session-header {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 16px;
  cursor: pointer;
  user-select: none;
}

.session-header:hover {
  background: #1e2233;
}

.session-chevron {
  font-size: 0.7rem;
  color: #6b7280;
  flex-shrink: 0;
}

.session-meta {
  font-size: 0.92rem;
  color: #e2e8f0;
}

.session-body {
  padding: 0 12px 12px;
}

.seg-card {
  background: #1e2130;
  border-radius: 6px;
  padding: 12px 16px;
  margin: 8px 0;
}

.seg-header {
  font-size: 0.78rem;
  color: #6b7280;
  margin-bottom: 8px;
  font-weight: 500;
}

.seg-video {
  width: 100%;
  max-height: 240px;
  border-radius: 4px;
  display: block;
  margin-bottom: 10px;
  background: #000;
}

.dl-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.dl-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid;
  background: transparent;
  font-size: 0.78rem;
  text-decoration: none;
  transition: opacity 0.15s;
}

.dl-pill:hover {
  opacity: 0.75;
}
```

- [ ] **Step 2: Remove old recordings CSS if present**

Search `style.css` for any `.session`, `.segment`, `.downloads`, or `details` selectors that were part of the old `<details>` tree. Remove them to avoid conflicts.

- [ ] **Step 3: Commit**

```bash
cd /home/ryan/claude/sunny-data
git add app/static/style.css
git commit -m "feat: add CSS for date-grouped recordings UI"
```

---

## Task 5: Deploy to Unraid and verify

**Files:** None (deployment only)

- [ ] **Step 1: Push to GitHub**

```bash
cd /home/ryan/claude/sunny-data
git push origin HEAD:main HEAD:master
```

- [ ] **Step 2: Pull, rebuild, and recreate container on Unraid**

```bash
ssh root@10.0.0.39 "cd /mnt/user/appdata/sunny-data-src && git pull && docker build -t sunny-data:latest . && docker stop sunny-data && docker rm sunny-data && docker run -d --name sunny-data -p 8082:8080 -v /mnt/user/appdata/sunny-data:/app/data -v /mnt/user/Recordings:/recordings --restart unless-stopped sunny-data:latest"
```

- [ ] **Step 3: Verify API returns expected shape**

```bash
ssh root@10.0.0.39 "curl -s http://localhost:8082/api/recordings | python3 -c \"
import sys, json
d = json.load(sys.stdin)
print(len(d), 'date groups')
for g in d:
    print(' ', g['date_label'], '-', len(g['sessions']), 'sessions')
    for s in g['sessions']:
        print('   ', s['start_label'], s['duration_min'], 'min', len(s['segments']), 'segs')
\""
```

Expected: date groups with readable labels, sessions with time + duration.

- [ ] **Step 4: Open the UI and confirm visually**

Open `http://tower.local:8082` (or `http://10.0.0.39:8082`), go to the Recordings tab. Confirm:
- Date headers render with horizontal rules
- Sessions show `▶ 7:03 PM · 14 min · 14 segments` collapsed
- Clicking a session expands it and collapses any previously open one
- Segment cards show video player (for segments with `qcamera.ts`) and colored download pills
- Clicking another session collapses the first
