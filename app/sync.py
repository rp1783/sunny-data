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
    _sync_queue.put(None)  # sentinel — signals SSE generator to stop
    _sync_running.clear()


async def sse_generator() -> AsyncGenerator[str, None]:
    loop = asyncio.get_event_loop()
    while True:
        item = await loop.run_in_executor(None, _sync_queue.get)
        if item is None:
            yield "data: __DONE__\n\n"
            break
        yield f"data: {item.rstrip()}\n\n"
