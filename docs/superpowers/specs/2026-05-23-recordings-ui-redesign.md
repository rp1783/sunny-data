# Recordings Tab UI Redesign

**Date:** 2026-05-23  
**Status:** Approved

## Goal

Replace the opaque route-ID tree with a human-readable, date-grouped recording browser. Sessions show start time and duration; segments show an inline video preview and download links.

---

## Data Layer

### `build_recording_tree()` changes (`app/recordings.py`)

The flat layout groups `routeId--segN/` folders by prefix. Extend this with:

1. **Session start time** — read `os.path.getmtime()` of the `--0` segment folder for each session.
2. **Per-segment time labels** — `start_time + seg_index × 60 seconds`, formatted as `"7:03 – 7:04 PM"`.
3. **Duration** — `len(segments)` minutes.
4. **Date grouping** — group sessions by calendar date (local time), sort dates newest-first, sort sessions within a date newest-first.

### New API response shape (`GET /api/recordings`)

```json
[
  {
    "date": "2026-05-22",
    "date_label": "Thursday, May 22",
    "sessions": [
      {
        "session": "00000000--e8e9b1e3c0",
        "start_label": "7:03 PM",
        "duration_min": 14,
        "segments": [
          {
            "path": "realdata/00000000--e8e9b1e3c0--0",
            "index": 0,
            "time_label": "7:03 – 7:04 PM",
            "files": ["qcamera.ts", "ecamera.hevc", "fcamera.hevc", "qlog.zst", "rlog.zst"]
          }
        ]
      }
    ]
  }
]
```

**File ordering within a segment:** `qcamera.ts` first (if present), then remaining files alphabetically.

The nested layout (legacy `session/segN/files`) continues to work unchanged; its sessions use folder mtime in the same way.

---

## UI Components (`app/static/`)

### Date group header

Full-width row with a small-caps date label and a subtle horizontal rule.

```
── Thursday, May 22 ─────────────────────────────
```

Color: `#6b7280`. No interactive behavior.

### Session card

- **Collapsed** (default): single header row — `▶  7:03 PM  ·  14 min  ·  14 segments`
- **Expanded**: header changes chevron to `▼`; segment cards render below
- Click anywhere on the header toggles expand/collapse
- **Only one session open at a time** — opening a new session collapses the previous one
- Left border accent: `3px solid #3b82f6`
- Background: `#1a1d27`, `border-radius: 8px`

### Segment card

Visible only when parent session is expanded.

- Header: `Segment 1  ·  7:03 – 7:04 PM` (muted text, single line)
- Video player: rendered only if `qcamera.ts` is in `files`. `width: 100%`, `max-height: 240px`, `border-radius: 4px`, `preload="metadata"`.
- Download links: pill-shaped flex row below the video. Icon + filename. Color by type:
  - `.ts` → green (`#86efac`)
  - `.hevc` → blue (`#93c5fd`)
  - `.zst` / other → gray (`#9ca3af`)
- Background: `#1e2130`, slightly inset from the session card

### Empty state

Centered, muted text: `"No recordings yet — run a sync to pull from your device."`

---

## Styling

- Base theme unchanged: `#0f1117` page background
- Date headers use `letter-spacing`, `text-transform: uppercase`, `font-size: 0.75rem`
- Session cards have `margin-bottom: 8px`, `cursor: pointer` on header
- Segment cards have `padding: 12px 16px`, `margin: 8px 0`
- Download pill: `padding: 4px 10px`, `border-radius: 999px`, `border: 1px solid`, background transparent

---

## What Does Not Change

- The `/files/{path}` file-serving endpoint — unchanged
- Settings, Sync tabs — unchanged
- The `resolve_file_path()` traversal guard — unchanged
- XSS protection via `escHtml()` — applied to all dynamic text in the new template

---

## Out of Scope

- Filtering or search
- Thumbnails from video frames
- Deleting recordings from the UI
- Any change to how files are synced or stored
