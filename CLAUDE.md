# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this project is

**sunny-data** is a Docker-based web app for syncing and browsing [Comma 4](https://comma.ai) dashcam recordings from a local network. It runs on Unraid, exposes a browser UI on port 8080, and pulls recordings via rsync over SSH.

## Development commands

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt

# Run all tests
pytest tests/ -v

# Run a single test file
pytest tests/test_recordings.py -v

# Run a single test
pytest tests/test_recordings.py::test_name -v

# Run the dev server (from project root — conftest.py adds app/ to sys.path)
cd app && uvicorn main:app --reload --port 8080

# Build the Docker image
docker build -t sunny-data:latest .
```

## Architecture

**Backend** — FastAPI app in `app/`. Modules are imported directly (not as a package), so `conftest.py` inserts `app/` into `sys.path` for tests.

| Module | Responsibility |
|---|---|
| `main.py` | FastAPI app, all API routes, static file mount |
| `config.py` | `AppConfig` Pydantic model; read/write `config.json` and `ssh_key` under `DATA_DIR` (`/app/data`) |
| `sync.py` | Runs rsync in a background thread; broadcasts live output via SSE to all connected clients using a subscriber queue pattern; triggers stitching and cleanup on success |
| `recordings.py` | Walks the recordings directory and builds a JSON tree grouped by date; handles both **nested** layout (`session/0/`, `session/1/`) and **flat** layout (`session--0/`, `session--1/`) |
| `stitching.py` | Uses ffmpeg to concat per-camera `.hevc` segments into H.264 `.mp4` files under `stitched/`; generates a `.jpg` thumbnail; skips segments already stitched |
| `cleanup.py` | Deletes raw segments and stitched files for sessions older than 30 days that aren't starred |
| `starred.py` | Persists starred session names to `DATA_DIR/starred.json` |
| `log_buffer.py` | In-memory ring buffer for structured log capture, exposed at `/api/logs` |

**Frontend** — Single-page app in `app/static/` (plain HTML/CSS/JS, no build step). The FastAPI static mount serves it as a fallback after all API routes.

**Recordings layout** — Two layouts are auto-detected at runtime:
- Nested: `/recordings/realdata/<session>/<segment_index>/` (original Comma device layout)
- Flat: `/recordings/realdata/<session>--<segment_index>/` (after some filesystem operations)

Stitched videos land in `/recordings/stitched/<session>--<camera>.mp4`.

## Runtime data paths

- `DATA_DIR` defaults to `/app/data`, overridable via env var `DATA_DIR`
- `config.json` and `ssh_key` are stored in `DATA_DIR`
- Recordings are mounted at `/recordings` (configurable via the UI as `local_path`)

## Testing

Tests use `httpx.AsyncClient` / `TestClient` against the FastAPI app. The `conftest.py` at the root adds `app/` to `sys.path` — tests import app modules directly. There are no mocked subprocess calls; stitching/sync tests stub at the function level.
