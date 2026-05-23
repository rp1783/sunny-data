# sunny-data Docker + Web UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dockerize the sunny-data rsync script and deploy to Unraid with a FastAPI web UI for browsing recordings, triggering syncs, and managing config/schedule.

**Architecture:** Single Python 3.12 container running FastAPI + uvicorn, serving both REST API and plain HTML/JS/CSS frontend. APScheduler handles the cron schedule in-process. Two Unraid volumes: appdata (config, SSH key) and Recordings share. Unraid community app XML template included for one-click install.

**Tech Stack:** Python 3.12, FastAPI 0.115, uvicorn, APScheduler 3.10, croniter 2.0, pydantic 2.x, rsync, openssh-client, plain HTML/CSS/JS (no build step), Docker

---

## File Map

| Path (repo) | Container path | Responsibility |
|---|---|---|
| `app/config.py` | `/app/config.py` | Config model, read/write/validate, SSH key save |
| `app/recordings.py` | `/app/recordings.py` | Walk recordings directory, path-safe file resolution |
| `app/sync.py` | `/app/sync.py` | rsync subprocess, SSE queue, in-memory sync state |
| `app/main.py` | `/app/main.py` | FastAPI app, all routes, APScheduler lifespan |
| `app/static/index.html` | `/app/static/index.html` | Three-tab single-page UI shell |
| `app/static/style.css` | `/app/static/style.css` | Dark theme, layout, component styles |
| `app/static/app.js` | `/app/static/app.js` | Tab logic, recordings tree, sync stream, settings form |
| `Dockerfile` | — | Build: python:3.12-slim + rsync + openssh-client |
| `requirements.txt` | `/app/requirements.txt` | Runtime Python dependencies |
| `requirements-dev.txt` | — | Test dependencies |
| `conftest.py` | — | Adds `app/` to sys.path for tests |
| `tests/test_config.py` | — | Unit tests for config module |
| `tests/test_recordings.py` | — | Unit tests for recordings module |
| `tests/test_sync.py` | — | Unit tests for sync module |
| `tests/test_api.py` | — | Integration tests for all API endpoints |
| `sunny-data.xml` | — | Unraid community app template |

---

### Task 1: Scaffold project — fetch repo files, create directory structure, Dockerfile, requirements

**Files:**
- Fetch from GitHub: `pull_recordings.sh`, `pull_recordings.conf.example`, `.gitignore`
- Create: `Dockerfile`
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `conftest.py`
- Create: `app/__init__.py` (empty)
- Create: `app/static/` (empty directory placeholder)

- [ ] **Step 1: Fetch existing repo files into working directory**

```bash
cd /home/ryan/claude/sunny-data
gh api repos/rp1783/sunny-data/contents/pull_recordings.sh | jq -r '.content' | base64 -d > pull_recordings.sh
gh api repos/rp1783/sunny-data/contents/pull_recordings.conf.example | jq -r '.content' | base64 -d > pull_recordings.conf.example
gh api repos/rp1783/sunny-data/contents/.gitignore | jq -r '.content' | base64 -d > .gitignore
```

Expected: three files created with no errors.

- [ ] **Step 2: Create directory structure**

```bash
mkdir -p app/static tests
touch app/__init__.py app/static/.gitkeep
```

- [ ] **Step 3: Write `requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
apscheduler==3.10.4
croniter==2.0.5
pydantic==2.8.2
```

- [ ] **Step 4: Write `requirements-dev.txt`**

```
pytest==8.3.2
requests==2.32.3
httpx==0.27.0
```

- [ ] **Step 5: Write `conftest.py`**

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent / "app"))
```

- [ ] **Step 6: Write `Dockerfile`**

```dockerfile
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    rsync \
    openssh-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ .

EXPOSE 8080

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

- [ ] **Step 7: Git init and initial commit**

```bash
cd /home/ryan/claude/sunny-data
git init
git add .
git commit -m "chore: scaffold project structure and Dockerfile"
```

Expected: git repository initialized, initial commit created.

---

### Task 2: Config module with tests

**Files:**
- Create: `app/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write failing tests**

`tests/test_config.py`:
```python
import pytest
from pathlib import Path
import config as config_mod
from config import AppConfig, load_config, save_config, save_ssh_key, is_config_complete


def test_load_config_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path)
    assert load_config() is None


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path)
    cfg = AppConfig(
        device_ip="10.0.0.1", device_user="comma", ssh_port=22,
        remote_path="/data/", local_path="/recordings", schedule="0 * * * *",
    )
    save_config(cfg)
    loaded = load_config()
    assert loaded is not None
    assert loaded.device_ip == "10.0.0.1"
    assert loaded.schedule == "0 * * * *"


def test_load_config_returns_none_on_corrupt_json(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path)
    (tmp_path / "config.json").write_text("not json")
    assert load_config() is None


def test_save_ssh_key_creates_file_with_600_permissions(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path)
    save_ssh_key("-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----\n")
    key_file = tmp_path / "ssh_key"
    assert key_file.exists()
    assert oct(key_file.stat().st_mode)[-3:] == "600"


def test_is_config_complete_false_when_none():
    assert not is_config_complete(None)


def test_is_config_complete_false_when_empty_ip():
    cfg = AppConfig(
        device_ip="", device_user="comma", ssh_port=22,
        remote_path="/data/", local_path="/recordings", schedule="0 * * * *",
    )
    assert not is_config_complete(cfg)


def test_is_config_complete_true_when_all_set():
    cfg = AppConfig(
        device_ip="10.0.0.1", device_user="comma", ssh_port=22,
        remote_path="/data/", local_path="/recordings", schedule="0 * * * *",
    )
    assert is_config_complete(cfg)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
cd /home/ryan/claude/sunny-data
pip install -r requirements.txt -r requirements-dev.txt -q
pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'config'`

- [ ] **Step 3: Write `app/config.py`**

```python
import json
import os
from pathlib import Path

from pydantic import BaseModel

DATA_DIR = Path(os.environ.get("DATA_DIR", "/app/data"))


class AppConfig(BaseModel):
    device_ip: str = ""
    device_user: str = "comma"
    ssh_port: int = 22
    remote_path: str = "/data/media/0/realdata/"
    local_path: str = "/recordings"
    schedule: str = "0 * * * *"


def config_path() -> Path:
    return DATA_DIR / "config.json"


def ssh_key_path() -> Path:
    return DATA_DIR / "ssh_key"


def load_config() -> AppConfig | None:
    p = config_path()
    if not p.exists():
        return None
    try:
        return AppConfig(**json.loads(p.read_text()))
    except Exception:
        return None


def save_config(config: AppConfig) -> None:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(config.model_dump_json(indent=2))


def save_ssh_key(key: str) -> None:
    p = ssh_key_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(key)
    p.chmod(0o600)


def is_config_complete(config: AppConfig | None) -> bool:
    if config is None:
        return False
    return bool(
        config.device_ip
        and config.device_user
        and config.remote_path
        and config.local_path
        and config.schedule
    )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_config.py -v
```

Expected: 7 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/config.py tests/test_config.py
git commit -m "feat: add config module with read/write/validate"
```

---

### Task 3: Recordings module with tests

**Files:**
- Create: `app/recordings.py`
- Create: `tests/test_recordings.py`

- [ ] **Step 1: Write failing tests**

`tests/test_recordings.py`:
```python
from pathlib import Path
from recordings import build_recording_tree, resolve_file_path


def _make_segment(base: Path, session: str, segment: str, files: list[str]) -> None:
    seg_dir = base / "realdata" / session / segment
    seg_dir.mkdir(parents=True)
    for f in files:
        (seg_dir / f).write_text("data")


def test_build_tree_empty_when_no_realdata_dir(tmp_path):
    assert build_recording_tree(str(tmp_path)) == []


def test_build_tree_single_session_single_segment(tmp_path):
    _make_segment(tmp_path, "2024-11-15--08-32-10", "0", ["qcamera.ts", "fcamera.hevc", "rlog.bz2"])
    result = build_recording_tree(str(tmp_path))
    assert len(result) == 1
    assert result[0]["session"] == "2024-11-15--08-32-10"
    assert len(result[0]["segments"]) == 1
    assert result[0]["segments"][0]["segment"] == "0"
    assert set(result[0]["segments"][0]["files"]) == {"qcamera.ts", "fcamera.hevc", "rlog.bz2"}


def test_build_tree_multiple_segments_sorted(tmp_path):
    for seg in ["2", "0", "1"]:
        _make_segment(tmp_path, "2024-11-15--08-32-10", seg, ["qcamera.ts"])
    result = build_recording_tree(str(tmp_path))
    segments = [s["segment"] for s in result[0]["segments"]]
    assert segments == ["0", "1", "2"]


def test_build_tree_skips_empty_segments(tmp_path):
    (tmp_path / "realdata" / "2024-11-15--08-32-10" / "0").mkdir(parents=True)
    result = build_recording_tree(str(tmp_path))
    assert result == []


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

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_recordings.py -v
```

Expected: `ModuleNotFoundError: No module named 'recordings'`

- [ ] **Step 3: Write `app/recordings.py`**

```python
from pathlib import Path


def build_recording_tree(local_path: str) -> list:
    base = Path(local_path) / "realdata"
    if not base.exists():
        return []

    sessions = []
    for session_dir in sorted(base.iterdir()):
        if not session_dir.is_dir():
            continue
        segments = []
        for seg_dir in sorted(
            session_dir.iterdir(),
            key=lambda p: int(p.name) if p.name.isdigit() else p.name,
        ):
            if not seg_dir.is_dir():
                continue
            files = sorted(f.name for f in seg_dir.iterdir() if f.is_file())
            if files:
                segments.append({"segment": seg_dir.name, "files": files})
        if segments:
            sessions.append({"session": session_dir.name, "segments": segments})

    return sessions


def resolve_file_path(local_path: str, rel_path: str) -> Path | None:
    base = Path(local_path).resolve()
    target = (base / rel_path).resolve()
    if not str(target).startswith(str(base) + "/") and target != base:
        return None
    if not target.is_file():
        return None
    return target
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_recordings.py -v
```

Expected: 7 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/recordings.py tests/test_recordings.py
git commit -m "feat: add recordings tree walker with path traversal protection"
```

---

### Task 4: Sync module with tests

**Files:**
- Create: `app/sync.py`
- Create: `tests/test_sync.py`

- [ ] **Step 1: Write failing tests**

`tests/test_sync.py`:
```python
import time
from unittest.mock import MagicMock, patch
import pytest
import sync as sync_mod
from sync import run_sync, is_sync_running
from config import AppConfig


def _cfg():
    return AppConfig(
        device_ip="10.0.0.1", device_user="comma", ssh_port=22,
        remote_path="/data/", local_path="/recordings", schedule="0 * * * *",
    )


@pytest.fixture(autouse=True)
def reset_sync(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_mod, "LAST_SYNC_PATH", tmp_path / "last_sync.json")
    sync_mod._sync_running.clear()
    while not sync_mod._sync_queue.empty():
        try:
            sync_mod._sync_queue.get_nowait()
        except Exception:
            break
    yield
    sync_mod._sync_running.clear()


def test_is_sync_running_initially_false():
    assert not is_sync_running()


def test_run_sync_raises_if_already_running():
    sync_mod._sync_running.set()
    with pytest.raises(RuntimeError, match="sync_already_running"):
        run_sync(_cfg())


def test_run_sync_writes_last_sync_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_mod, "LAST_SYNC_PATH", tmp_path / "last_sync.json")
    mock_proc = MagicMock()
    mock_proc.stdout = iter(["syncing...\n"])
    mock_proc.returncode = 0
    mock_proc.wait.return_value = None
    with patch("subprocess.Popen", return_value=mock_proc):
        run_sync(_cfg())
        for _ in range(30):
            if not is_sync_running():
                break
            time.sleep(0.1)
    assert (tmp_path / "last_sync.json").exists()
    import json
    data = json.loads((tmp_path / "last_sync.json").read_text())
    assert data["status"] == "success"
    assert data["exit_code"] == 0


def test_run_sync_records_error_on_nonzero_exit(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_mod, "LAST_SYNC_PATH", tmp_path / "last_sync.json")
    mock_proc = MagicMock()
    mock_proc.stdout = iter(["error output\n"])
    mock_proc.returncode = 23
    mock_proc.wait.return_value = None
    with patch("subprocess.Popen", return_value=mock_proc):
        run_sync(_cfg())
        for _ in range(30):
            if not is_sync_running():
                break
            time.sleep(0.1)
    import json
    data = json.loads((tmp_path / "last_sync.json").read_text())
    assert data["status"] == "error"
    assert data["exit_code"] == 23


def test_run_sync_clears_running_flag_on_completion(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_mod, "LAST_SYNC_PATH", tmp_path / "last_sync.json")
    mock_proc = MagicMock()
    mock_proc.stdout = iter([])
    mock_proc.returncode = 0
    mock_proc.wait.return_value = None
    with patch("subprocess.Popen", return_value=mock_proc):
        run_sync(_cfg())
        for _ in range(30):
            if not is_sync_running():
                break
            time.sleep(0.1)
    assert not is_sync_running()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_sync.py -v
```

Expected: `ModuleNotFoundError: No module named 'sync'`

- [ ] **Step 3: Write `app/sync.py`**

```python
import asyncio
import json
import queue
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from config import AppConfig, ssh_key_path

LAST_SYNC_PATH = Path("/app/data/last_sync.json")

_sync_queue: queue.Queue = queue.Queue()
_sync_running = threading.Event()


def is_sync_running() -> bool:
    return _sync_running.is_set()


def get_last_sync() -> dict:
    if LAST_SYNC_PATH.exists():
        try:
            return json.loads(LAST_SYNC_PATH.read_text())
        except Exception:
            pass
    return {}


def run_sync(config: AppConfig) -> None:
    if _sync_running.is_set():
        raise RuntimeError("sync_already_running")
    _sync_running.set()
    thread = threading.Thread(target=_sync_worker, args=(config,), daemon=True)
    thread.start()


def _sync_worker(config: AppConfig) -> None:
    key = str(ssh_key_path())
    cmd = [
        "rsync",
        "--archive",
        "--ignore-existing",
        "--compress",
        "--partial",
        "--progress",
        "-e",
        f"ssh -i {key} -p {config.ssh_port} -o StrictHostKeyChecking=no -o BatchMode=yes",
        f"{config.device_user}@{config.device_ip}:{config.remote_path}",
        config.local_path,
    ]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _sync_queue.put(f"[{ts}] Starting sync...\n")

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            _sync_queue.put(line)
        proc.wait()
        rc = proc.returncode
    except Exception as exc:
        _sync_queue.put(f"ERROR: {exc}\n")
        rc = 1

    status = "success" if rc == 0 else "error"
    ts = datetime.now().isoformat()
    result = {"status": status, "timestamp": ts, "exit_code": rc}
    LAST_SYNC_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_SYNC_PATH.write_text(json.dumps(result, indent=2))

    done_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    word = "complete" if rc == 0 else "failed"
    _sync_queue.put(f"[{done_ts}] Sync {word} (exit code {rc}).\n")
    _sync_queue.put(None)  # sentinel
    _sync_running.clear()


async def sse_generator() -> AsyncGenerator[str, None]:
    loop = asyncio.get_event_loop()
    while True:
        item = await loop.run_in_executor(None, _sync_queue.get)
        if item is None:
            yield "data: __DONE__\n\n"
            break
        yield f"data: {item.rstrip()}\n\n"
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_sync.py -v
```

Expected: 5 tests PASSED.

- [ ] **Step 5: Commit**

```bash
git add app/sync.py tests/test_sync.py
git commit -m "feat: add sync module with rsync subprocess and SSE queue"
```

---

### Task 5: FastAPI main app with API integration tests

**Files:**
- Create: `app/main.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write failing API tests**

`tests/test_api.py`:
```python
import pytest
from fastapi.testclient import TestClient
import config as config_mod
import sync as sync_mod


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path)
    monkeypatch.setattr(sync_mod, "LAST_SYNC_PATH", tmp_path / "last_sync.json")
    from main import app
    with TestClient(app) as c:
        yield c


def test_get_config_empty_before_setup(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    assert res.json() == {}


def test_post_and_get_config_roundtrip(client):
    payload = {
        "device_ip": "10.0.0.1", "device_user": "comma", "ssh_port": 22,
        "remote_path": "/data/", "local_path": "/recordings", "schedule": "0 * * * *",
    }
    res = client.post("/api/config", json=payload)
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    res2 = client.get("/api/config")
    assert res2.json()["device_ip"] == "10.0.0.1"
    assert res2.json()["schedule"] == "0 * * * *"


def test_post_config_rejects_invalid_cron(client):
    payload = {
        "device_ip": "10.0.0.1", "device_user": "comma", "ssh_port": 22,
        "remote_path": "/data/", "local_path": "/recordings", "schedule": "not-a-cron",
    }
    res = client.post("/api/config", json=payload)
    assert res.status_code == 422


def test_post_ssh_key_saves_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path)
    res = client.post(
        "/api/ssh-key",
        json={"key": "-----BEGIN OPENSSH PRIVATE KEY-----\ntest\n-----END OPENSSH PRIVATE KEY-----"},
    )
    assert res.status_code == 200
    assert (tmp_path / "ssh_key").exists()


def test_post_ssh_key_rejects_non_key(client):
    res = client.post("/api/ssh-key", json={"key": "notakey"})
    assert res.status_code == 422


def test_sync_run_returns_409_when_already_running(client):
    sync_mod._sync_running.set()
    try:
        res = client.post("/api/sync/run")
        assert res.status_code == 409
    finally:
        sync_mod._sync_running.clear()


def test_sync_run_returns_400_when_config_missing(client):
    res = client.post("/api/sync/run")
    assert res.status_code == 400


def test_sync_status_returns_not_running(client):
    res = client.get("/api/sync/status")
    assert res.status_code == 200
    data = res.json()
    assert data["running"] is False


def test_get_recordings_empty_when_no_config(client):
    res = client.get("/api/recordings")
    assert res.status_code == 200
    assert res.json() == []


def test_serve_file_returns_404_for_missing_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path)
    payload = {
        "device_ip": "10.0.0.1", "device_user": "comma", "ssh_port": 22,
        "remote_path": "/data/", "local_path": str(tmp_path), "schedule": "0 * * * *",
    }
    client.post("/api/config", json=payload)
    res = client.get("/files/realdata/nosession/0/qcamera.ts")
    assert res.status_code == 404


def test_serve_file_blocks_path_traversal(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path)
    payload = {
        "device_ip": "10.0.0.1", "device_user": "comma", "ssh_port": 22,
        "remote_path": "/data/", "local_path": str(tmp_path), "schedule": "0 * * * *",
    }
    client.post("/api/config", json=payload)
    res = client.get("/files/../etc/passwd")
    assert res.status_code in (404, 403, 422)
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_api.py -v
```

Expected: `ModuleNotFoundError: No module named 'main'`

- [ ] **Step 3: Write `app/main.py`**

```python
import os
from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from croniter import croniter
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from config import (
    AppConfig,
    is_config_complete,
    load_config,
    save_config,
    save_ssh_key,
    ssh_key_path,
)
from recordings import build_recording_tree, resolve_file_path
from sync import get_last_sync, is_sync_running, run_sync, sse_generator

scheduler = BackgroundScheduler()


def _scheduled_sync() -> None:
    config = load_config()
    if config and is_config_complete(config):
        try:
            run_sync(config)
        except RuntimeError:
            pass  # already running


@asynccontextmanager
async def lifespan(app: FastAPI):
    scheduler.start()
    config = load_config()
    if config and is_config_complete(config):
        scheduler.add_job(
            _scheduled_sync,
            CronTrigger.from_crontab(config.schedule),
            id="sync_job",
            replace_existing=True,
        )
    yield
    scheduler.shutdown()


app = FastAPI(lifespan=lifespan)


class ConfigPayload(BaseModel):
    device_ip: str
    device_user: str
    ssh_port: int
    remote_path: str
    local_path: str
    schedule: str


class SshKeyPayload(BaseModel):
    key: str


@app.get("/api/config")
def get_config():
    config = load_config()
    if config is None:
        return {}
    data = config.model_dump()
    data["ssh_key_set"] = ssh_key_path().exists()
    return data


@app.post("/api/config")
def post_config(payload: ConfigPayload):
    if not croniter.is_valid(payload.schedule):
        raise HTTPException(status_code=422, detail="Invalid cron expression")
    config = AppConfig(**payload.model_dump())
    save_config(config)
    if scheduler.get_job("sync_job"):
        scheduler.remove_job("sync_job")
    scheduler.add_job(
        _scheduled_sync,
        CronTrigger.from_crontab(config.schedule),
        id="sync_job",
        replace_existing=True,
    )
    return {"ok": True}


@app.post("/api/ssh-key")
def post_ssh_key(payload: SshKeyPayload):
    key = payload.key.strip()
    if not key or not key.startswith("-----BEGIN"):
        raise HTTPException(status_code=422, detail="Invalid SSH key")
    save_ssh_key(key + "\n")
    return {"ok": True}


@app.post("/api/sync/run")
def trigger_sync():
    if is_sync_running():
        raise HTTPException(status_code=409, detail="Sync already in progress")
    config = load_config()
    if not config or not is_config_complete(config):
        raise HTTPException(status_code=400, detail="Configuration incomplete")
    run_sync(config)
    return {"ok": True}


@app.get("/api/sync/stream")
async def sync_stream():
    return StreamingResponse(sse_generator(), media_type="text/event-stream")


@app.get("/api/sync/status")
def sync_status():
    return {"running": is_sync_running(), "last_sync": get_last_sync()}


@app.get("/api/recordings")
def get_recordings():
    config = load_config()
    if not config:
        return []
    return build_recording_tree(config.local_path)


@app.get("/files/{path:path}")
def serve_file(path: str):
    config = load_config()
    if not config:
        raise HTTPException(status_code=400, detail="Configuration incomplete")
    file_path = resolve_file_path(config.local_path, path)
    if file_path is None:
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path=str(file_path))


STATIC_DIR = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")
```

- [ ] **Step 4: Run all tests to confirm they pass**

```bash
pytest tests/test_config.py tests/test_recordings.py tests/test_sync.py tests/test_api.py -v
```

Expected: all tests PASSED. (The `test_api.py` suite should show ~10 PASSED.)

- [ ] **Step 5: Commit**

```bash
git add app/main.py tests/test_api.py
git commit -m "feat: add FastAPI main app with all API routes and APScheduler"
```

---

### Task 6: Frontend HTML and CSS

**Files:**
- Create: `app/static/index.html`
- Create: `app/static/style.css`

- [ ] **Step 1: Write `app/static/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>sunny-data</title>
  <link rel="stylesheet" href="/style.css">
</head>
<body>
  <div id="banner" class="banner hidden"></div>

  <nav>
    <button class="tab-btn active" data-tab="recordings">Recordings</button>
    <button class="tab-btn" data-tab="sync">Sync</button>
    <button class="tab-btn" data-tab="settings">Settings</button>
  </nav>

  <div id="tab-recordings" class="tab-panel">
    <div id="recordings-tree"><p class="muted">Loading...</p></div>
  </div>

  <div id="tab-sync" class="tab-panel hidden">
    <div class="sync-header">
      <span id="last-sync-label" class="muted">Last sync: —</span>
      <span id="sync-badge"></span>
    </div>
    <button id="pull-now-btn">Pull Now</button>
    <pre id="sync-log"></pre>
  </div>

  <div id="tab-settings" class="tab-panel hidden">
    <form id="settings-form">
      <label>Device IP
        <input name="device_ip" type="text" placeholder="192.168.1.x">
      </label>
      <label>Device User
        <input name="device_user" type="text" placeholder="comma">
      </label>
      <label>SSH Port
        <input name="ssh_port" type="number" value="22" min="1" max="65535">
      </label>
      <label>Remote Path
        <input name="remote_path" type="text" placeholder="/data/media/0/realdata/">
      </label>
      <label>Local Path (container)
        <input name="local_path" type="text" placeholder="/recordings">
        <span class="hint">Use the container-internal path (e.g. /recordings)</span>
      </label>
      <label>SSH Private Key
        <textarea name="ssh_key" placeholder="Paste private key content here. Leave blank to keep existing key."></textarea>
      </label>

      <fieldset>
        <legend>Schedule</legend>
        <div id="schedule-simple" class="schedule-row">
          <span>Every</span>
          <input id="interval-value" type="number" min="1" max="999" value="1">
          <select id="interval-unit">
            <option value="hours">hours</option>
            <option value="minutes">minutes</option>
          </select>
        </div>
        <button type="button" id="toggle-advanced">Advanced ▾</button>
        <div id="schedule-advanced" class="hidden">
          <label>Cron expression
            <input name="schedule" type="text" placeholder="0 * * * *">
          </label>
          <div id="cron-preview" class="hint"></div>
        </div>
      </fieldset>

      <div id="settings-error" class="error hidden"></div>
      <button type="submit">Save Settings</button>
    </form>
  </div>

  <script src="/app.js"></script>
</body>
</html>
```

- [ ] **Step 2: Write `app/static/style.css`**

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  font-family: system-ui, -apple-system, sans-serif;
  background: #0f1117;
  color: #e0e0e0;
  font-size: 14px;
}

.hidden { display: none !important; }
.muted { color: #666; }
.hint { color: #5a7fbf; font-size: 12px; margin-top: 3px; }
.error { color: #f87171; font-size: 13px; }

/* Banner */
.banner {
  background: #92400e;
  color: #fde68a;
  padding: 10px 20px;
  font-size: 13px;
}

/* Nav */
nav {
  display: flex;
  gap: 2px;
  background: #1a1d27;
  padding: 8px 16px;
  border-bottom: 1px solid #2a2f3f;
}

.tab-btn {
  padding: 7px 18px;
  border: none;
  background: transparent;
  color: #888;
  cursor: pointer;
  border-radius: 4px;
  font-size: 13px;
  transition: background 0.15s;
}
.tab-btn:hover { background: #22263a; color: #ccc; }
.tab-btn.active { background: #2d3249; color: #fff; }

/* Tab panels */
.tab-panel { padding: 20px; max-width: 960px; margin: 0 auto; }

/* Settings form */
#settings-form {
  display: flex;
  flex-direction: column;
  gap: 14px;
  max-width: 580px;
}
#settings-form label {
  display: flex;
  flex-direction: column;
  gap: 5px;
  color: #aaa;
}
#settings-form input,
#settings-form textarea,
#settings-form select {
  padding: 8px 10px;
  background: #1e2130;
  border: 1px solid #353a52;
  border-radius: 4px;
  color: #e0e0e0;
  font-size: 13px;
  width: 100%;
}
#settings-form textarea {
  min-height: 90px;
  font-family: monospace;
  font-size: 12px;
  resize: vertical;
}
#settings-form input:focus,
#settings-form textarea:focus,
#settings-form select:focus {
  outline: none;
  border-color: #3b5bdb;
}
fieldset {
  border: 1px solid #353a52;
  border-radius: 4px;
  padding: 14px;
}
legend { padding: 0 6px; color: #aaa; font-size: 13px; }
.schedule-row {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #ccc;
}
.schedule-row input { width: 70px; }
.schedule-row select { width: auto; }
#toggle-advanced {
  margin-top: 10px;
  background: transparent;
  border: 1px solid #353a52;
  color: #888;
  padding: 4px 10px;
  border-radius: 4px;
  cursor: pointer;
  font-size: 12px;
}
#toggle-advanced:hover { color: #ccc; }
#schedule-advanced { margin-top: 10px; }
#cron-preview { margin-top: 4px; }
#settings-form button[type="submit"] {
  padding: 10px 28px;
  background: #3b5bdb;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 14px;
  align-self: flex-start;
  transition: background 0.15s;
}
#settings-form button[type="submit"]:hover { background: #4c6ef5; }

/* Sync tab */
.sync-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
}
.badge {
  padding: 2px 8px;
  border-radius: 12px;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
.badge-success { background: #14532d; color: #86efac; }
.badge-error { background: #7f1d1d; color: #fca5a5; }

#pull-now-btn {
  padding: 9px 22px;
  background: #3b5bdb;
  color: #fff;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 13px;
  margin-bottom: 14px;
}
#pull-now-btn:hover { background: #4c6ef5; }
#pull-now-btn:disabled { opacity: 0.45; cursor: not-allowed; }

#sync-log {
  background: #090d14;
  border: 1px solid #2a2f3f;
  border-radius: 4px;
  padding: 14px;
  font-family: 'Courier New', monospace;
  font-size: 12px;
  line-height: 1.5;
  min-height: 180px;
  max-height: 480px;
  overflow-y: auto;
  white-space: pre-wrap;
  color: #86efac;
}

/* Recordings */
.session {
  border: 1px solid #2a2f3f;
  border-radius: 5px;
  margin-bottom: 8px;
  overflow: hidden;
}
.session > summary {
  padding: 10px 14px;
  cursor: pointer;
  font-size: 13px;
  font-family: monospace;
  background: #1a1d27;
  list-style: none;
  user-select: none;
}
.session > summary:hover { background: #21263a; }
.session > summary::before { content: '▶ '; font-size: 10px; color: #555; }
.session[open] > summary::before { content: '▼ '; }

.segment {
  padding: 14px 16px;
  border-top: 1px solid #2a2f3f;
}
.segment-label {
  font-size: 11px;
  color: #555;
  margin-bottom: 8px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
video {
  width: 100%;
  max-width: 620px;
  border-radius: 4px;
  background: #000;
  display: block;
  margin-bottom: 10px;
}
.downloads {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.downloads a {
  font-size: 12px;
  color: #7ba4d4;
  background: #1e2130;
  padding: 4px 10px;
  border-radius: 4px;
  text-decoration: none;
  border: 1px solid #353a52;
  transition: background 0.15s;
}
.downloads a:hover { background: #2d3249; color: #a0c4f1; }
```

- [ ] **Step 3: Commit**

```bash
git add app/static/index.html app/static/style.css
git commit -m "feat: add frontend HTML shell and dark theme CSS"
```

---

### Task 7: Frontend JavaScript

**Files:**
- Create: `app/static/app.js`

- [ ] **Step 1: Write `app/static/app.js`**

```javascript
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
```

- [ ] **Step 2: Commit**

```bash
git add app/static/app.js
git commit -m "feat: add frontend JavaScript — tabs, recordings, sync stream, settings form"
```

---

### Task 8: Unraid community app template

**Files:**
- Create: `sunny-data.xml`

- [ ] **Step 1: Write `sunny-data.xml`**

```xml
<?xml version="1.0"?>
<Container version="2">
  <Name>sunny-data</Name>
  <Repository>sunny-data:latest</Repository>
  <Registry></Registry>
  <Network>bridge</Network>
  <Shell>bash</Shell>
  <Privileged>false</Privileged>
  <Overview>Sync and browse Comma 4 dashcam recordings. Pulls recordings via rsync/SSH, with a web UI to view recordings, trigger manual syncs, and configure the schedule.</Overview>
  <Category>Productivity: MediaApp:</Category>
  <WebUI>http://[IP]:[PORT:8080]/</WebUI>
  <Icon></Icon>
  <Config
    Name="Web UI Port"
    Target="8080"
    Default="8080"
    Mode="tcp"
    Description="Port for the sunny-data web interface."
    Type="Port"
    Display="always"
    Required="true"
    Mask="false">8080</Config>
  <Config
    Name="App Data"
    Target="/app/data"
    Default="/mnt/user/appdata/sunny-data"
    Mode="rw"
    Description="Stores config file, SSH key, and last-sync state."
    Type="Path"
    Display="always"
    Required="true"
    Mask="false">/mnt/user/appdata/sunny-data</Config>
  <Config
    Name="Recordings"
    Target="/recordings"
    Default="/mnt/user/Recordings"
    Mode="rw"
    Description="Share where recordings are synced to. Must exist on Unraid before starting the container."
    Type="Path"
    Display="always"
    Required="true"
    Mask="false">/mnt/user/Recordings</Config>
</Container>
```

- [ ] **Step 2: Commit**

```bash
git add sunny-data.xml
git commit -m "feat: add Unraid community app template"
```

---

### Task 9: Docker build and smoke test

- [ ] **Step 1: Run the full test suite one final time**

```bash
cd /home/ryan/claude/sunny-data
pytest tests/test_config.py tests/test_recordings.py tests/test_sync.py tests/test_api.py -v
```

Expected: all tests PASSED with no failures or errors.

- [ ] **Step 2: Build the Docker image**

```bash
docker build -t sunny-data:latest .
```

Expected: build completes with no errors. Final line: `Successfully tagged sunny-data:latest` or similar.

- [ ] **Step 3: Smoke test — start container and verify the UI loads**

```bash
docker run -d \
  --name sunny-data-test \
  -p 8080:8080 \
  -e DATA_DIR=/tmp/data \
  sunny-data:latest

sleep 3
curl -s -o /dev/null -w "%{http_code}" http://localhost:8080/
```

Expected: `200`

- [ ] **Step 4: Verify API endpoints respond**

```bash
curl -s http://localhost:8080/api/config
curl -s http://localhost:8080/api/sync/status
curl -s http://localhost:8080/api/recordings
```

Expected:
- `/api/config` → `{}`
- `/api/sync/status` → `{"running": false, "last_sync": {}}`
- `/api/recordings` → `[]`

- [ ] **Step 5: Stop and remove test container**

```bash
docker stop sunny-data-test && docker rm sunny-data-test
```

- [ ] **Step 6: Final commit**

```bash
git add .
git commit -m "chore: verify Docker build and smoke test passing"
```

---

## Unraid Deployment Notes

After building the image on your Unraid host (or transferring it):

1. **Create the Recordings share** in Unraid: Shares → Add Share → name it `Recordings`
2. **Create the appdata directory**: `/mnt/user/appdata/sunny-data/` (Unraid creates this automatically when the container first starts if using the template)
3. **Install via template**: Add `sunny-data.xml` as a Custom Template in the Unraid Docker UI, or use the XML to configure the container manually
4. **Configure**: Open the web UI at `http://unraid-ip:8080`, go to Settings, fill in device connection details and paste your SSH private key
5. **Local Path**: Set to `/recordings` (the container-internal path that maps to your Recordings share)
