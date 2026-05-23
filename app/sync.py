import asyncio
import json
import logging
import queue
import shlex
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from typing import AsyncGenerator

from config import AppConfig, DATA_DIR, ssh_key_path

_log = logging.getLogger(__name__)

LAST_SYNC_PATH = DATA_DIR / "last_sync.json"

_sync_lock = threading.Lock()
_sync_running = threading.Event()
_subscribers: list[queue.Queue] = []
_subscribers_lock = threading.Lock()


def _broadcast(item: object) -> None:
    with _subscribers_lock:
        for q in _subscribers:
            q.put(item)


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
    with _sync_lock:
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
        f"ssh -i {shlex.quote(key)} -p {config.ssh_port} -o StrictHostKeyChecking=no -o BatchMode=yes",
        f"{config.device_user}@{config.device_ip}:{config.remote_path}",
        config.local_path,
    ]
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    _broadcast(f"[{ts}] Starting sync...\n")

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        for line in proc.stdout:
            _broadcast(line)
        proc.wait()
        rc = proc.returncode
    except Exception as exc:
        _broadcast(f"ERROR: {exc}\n")
        rc = 1

    status = "success" if rc == 0 else "error"
    ts_iso = datetime.now().isoformat()
    result = {"status": status, "timestamp": ts_iso, "exit_code": rc}
    LAST_SYNC_PATH.parent.mkdir(parents=True, exist_ok=True)
    LAST_SYNC_PATH.write_text(json.dumps(result, indent=2))

    done_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    word = "complete" if rc == 0 else "failed"
    _broadcast(f"[{done_ts}] Sync {word} (exit code {rc}).\n")
    _broadcast(None)  # sentinel — signals all SSE generators to stop
    _sync_running.clear()


async def sse_generator() -> AsyncGenerator[str, None]:
    client_queue: queue.Queue = queue.Queue()
    with _subscribers_lock:
        _subscribers.append(client_queue)
        already_done = not _sync_running.is_set() and client_queue.empty()
    if already_done:
        with _subscribers_lock:
            try:
                _subscribers.remove(client_queue)
            except ValueError:
                pass
        yield "data: __DONE__\n\n"
        return
    loop = asyncio.get_running_loop()
    try:
        while True:
            item = await loop.run_in_executor(None, client_queue.get)
            if item is None:
                yield "data: __DONE__\n\n"
                break
            yield f"data: {item.rstrip()}\n\n"
    finally:
        with _subscribers_lock:
            try:
                _subscribers.remove(client_queue)
            except ValueError:
                pass
