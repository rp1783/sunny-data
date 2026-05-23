# sunny-data: Dockerized Unraid App with Web UI — Design Spec

**Date:** 2026-05-23
**Status:** Approved

---

## Overview

Dockerize the `sunny-data` rsync-over-SSH recording puller and deploy it to Unraid with a browser-based web UI. The UI provides: browsing and downloading recordings from a Comma 4 device, manually triggering a sync, and configuring the connection settings and cron schedule — all without touching the command line.

---

## Architecture

### Container

- **Base image:** `python:3.12-slim`
- **System packages installed at build time:** `rsync`, `openssh-client`
- **Runtime:** FastAPI + uvicorn (single process), APScheduler for scheduled sync jobs
- **Port:** `8080` (configurable via env var)
- **Single container** — no separate frontend container; FastAPI serves both the REST API and static HTML/JS/CSS

### Volumes (Unraid)

| Container path | Unraid path | Purpose |
|---|---|---|
| `/app/data` | `/mnt/user/appdata/sunny-data/` | Config, SSH key, sync logs |
| `/recordings` | `/mnt/user/Recordings/` | Synced recording files |

### Unraid install

An Unraid community app template (`sunny-data.xml`) is provided so the app can be installed from the Unraid UI. It pre-fills port mapping, volume paths, and any environment variables.

---

## Web UI

Single-page app in plain HTML/CSS/JS — no framework, no build step. Three tabs:

### Recordings Tab (default)

- File tree grouped by drive session (date-time folder) → segment number
- Sessions are collapsible rows
- Each segment shows:
  - Inline `<video>` player for `qcamera.ts` (low-res preview, browser-playable)
  - Download buttons for all files in the segment: `qcamera.ts`, `fcamera.hevc`, `rlog.bz2`
- Files served by FastAPI with `Content-Range` support for large file downloads

### Sync Tab

- "Pull Now" button — triggers an immediate rsync run
- Live log output streamed to a scrolling terminal-style box via SSE (Server-Sent Events)
- Last sync time and status (success / error) displayed

### Settings Tab

- **Connection fields:** Device IP, SSH port, SSH username, Remote path, Local path
- **SSH private key:** multi-line textarea; content stored as `/app/data/ssh_key` (chmod 600)
- **Schedule:**
  - Simple mode: interval picker (every N minutes or hours)
  - Advanced toggle: raw cron expression input with a human-readable preview line
- Save button — writes to disk and reschedules APScheduler live (no container restart needed)

---

## Data & Config

### Config file: `/app/data/config.json`

```json
{
  "device_ip": "192.168.1.x",
  "device_user": "comma",
  "ssh_port": 22,
  "remote_path": "/data/media/0/realdata/",
  "local_path": "/recordings",
  "schedule": "0 * * * *"
}
```

SSH key stored separately as `/app/data/ssh_key`.

### Sync execution flow

1. APScheduler fires on schedule, or user clicks "Pull Now" → `run_sync()` called in a background thread
2. `run_sync()` runs rsync as a subprocess, writing stdout/stderr line-by-line to an in-memory queue
3. SSE endpoint `GET /api/sync/stream` drains the queue to the browser in real time
4. On completion, `last_sync.json` written with timestamp and exit code

### Recordings browse flow

1. `GET /api/recordings` — walks `/recordings/realdata/`, returns JSON tree: sessions → segments → files
2. `GET /files/{path}` — streams the file with `Content-Range` support
3. Frontend renders the tree from JSON; `<video src="/files/...">` points at `.ts` files directly

### Settings save flow

1. `POST /api/config` — validates, writes `config.json`, reschedules APScheduler job
2. `POST /api/ssh-key` — writes key content to `/app/data/ssh_key`, sets permissions to 600

---

## Error Handling

### Sync errors

- rsync non-zero exit → error logged to SSE stream; `last_sync.json` records `status: "error"` and exit code; UI shows red status badge on Sync tab
- Device unreachable → same handling as above (rsync exits non-zero)
- Sync already running when "Pull Now" clicked → API returns 409; UI shows "Sync already in progress"

### Config validation (on save)

- IP format, port in range 1–65535, non-empty paths
- Cron expression parseable by `croniter` before accepting
- SSH key must be non-empty and begin with `-----BEGIN`; invalid key rejected with clear UI error

### Missing/corrupt config at startup

- If `config.json` absent or unparseable: app starts but scheduler does not run; UI shows banner on all tabs: "Configuration incomplete — go to Settings to set up"
- If `ssh_key` missing at sync time: sync fails immediately with a clear log message

### File serving

- Requests for paths outside `/recordings` → 403
- Non-existent files → 404

---

## File Structure (repo after implementation)

```
sunny-data/
├── Dockerfile
├── sunny-data.xml          # Unraid community app template
├── app/
│   ├── main.py             # FastAPI app, APScheduler setup
│   ├── sync.py             # rsync subprocess logic, SSE queue
│   ├── config.py           # config read/write, validation
│   ├── recordings.py       # file tree walker, file serving
│   └── static/
│       ├── index.html
│       ├── app.js
│       └── style.css
├── pull_recordings.sh      # kept for standalone use
├── pull_recordings.conf.example
└── tests/
    └── test_pull_recordings.bats
```

---

## Out of Scope

- Transcoding `.hevc` to mp4 for in-browser playback (download provided instead)
- User authentication / login (Unraid network is assumed trusted)
- Multi-device support
