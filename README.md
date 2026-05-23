# sunny-data

Sync and browse [Comma 4](https://comma.ai/shop/comma-4) dashcam recordings from your local network. Runs as a Docker container on Unraid with a web UI for viewing recordings, triggering syncs, and configuring the schedule.

![Recordings tab showing session browser with inline video preview and download links]

## Features

- **Recordings browser** — browse drive sessions and segments, play low-res preview (`qcamera.ts`) inline, download any file (`fcamera.hevc`, `rlog.bz2`, `qcamera.ts`)
- **Live sync** — "Pull Now" button streams rsync output in real time; last-sync status shown with success/error badge
- **Scheduled sync** — configure an interval (every N hours/minutes) or a raw cron expression; schedule updates without restarting the container
- **Settings UI** — paste your SSH private key and set device connection details entirely in the browser; no shell access needed after first setup

## Quick Start (Unraid)

### 1. Create a Recordings share

In the Unraid UI go to **Shares → Add Share** and create a share named `Recordings`.

### 2. Build or pull the image

On your Unraid host:

```bash
cd /path/to/sunny-data
docker build -t sunny-data:latest .
```

### 3. Add the container

Use the provided `sunny-data.xml` as a Custom Template in the Unraid Docker UI, or configure the container manually with these settings:

| Setting | Value |
|---|---|
| Repository | `sunny-data:latest` |
| Port | `8080` (host) → `8080` (container) |
| Path: App Data | `/mnt/user/appdata/sunny-data` → `/app/data` |
| Path: Recordings | `/mnt/user/Recordings` → `/recordings` |

### 4. Configure in the UI

Open `http://your-unraid-ip:8080`, go to the **Settings** tab and fill in:

| Field | Value |
|---|---|
| Device IP | IP of your Comma 4 on the local network |
| Device User | `comma` |
| SSH Port | `22` |
| Remote Path | `/data/media/0/realdata/` |
| Local Path | `/recordings` |
| SSH Private Key | Paste your private key (the key that's authorized on the device) |

Set your preferred sync schedule and click **Save Settings**.

## Running Without Unraid

```bash
docker run -d \
  --name sunny-data \
  -p 8080:8080 \
  -v /path/to/appdata:/app/data \
  -v /path/to/recordings:/recordings \
  sunny-data:latest
```

Open `http://localhost:8080`.

## Recordings Structure

The Comma device organizes recordings as:

```
/recordings/realdata/
└── 2024-11-15--08-32-10/      # drive session (date--time)
    ├── 0/
    │   ├── fcamera.hevc       # full-resolution front camera
    │   ├── qcamera.ts         # low-res preview (browser-playable)
    │   └── rlog.bz2           # route log
    ├── 1/
    │   └── ...
    └── ...
```

Each top-level folder is one drive. Numbered subdirectories are one-minute segments.

## Standalone Script

The original `pull_recordings.sh` bash script is still included for use without Docker:

```bash
cp pull_recordings.conf.example pull_recordings.conf
# edit pull_recordings.conf with your values
./pull_recordings.sh
```

See the script's inline comments for cron setup.

## Development

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run tests
pytest tests/ -v

# Run locally (no Docker)
cd app
uvicorn main:app --reload --port 8080
```

Tests cover config, recordings tree walker, sync module, and all API endpoints (30 tests).

## Tech Stack

- **Backend** — Python 3.12, FastAPI, APScheduler, rsync
- **Frontend** — plain HTML/CSS/JS (no build step)
- **Container** — python:3.12-slim, non-root user
