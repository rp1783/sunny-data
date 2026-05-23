import json
import time
from unittest.mock import MagicMock, patch

import pytest

import sync as sync_mod
from config import AppConfig
from sync import is_sync_running, run_sync


def _cfg():
    return AppConfig(
        device_ip="10.0.0.1",
        device_user="comma",
        ssh_port=22,
        remote_path="/data/",
        local_path="/recordings",
        schedule="0 * * * *",
    )


@pytest.fixture(autouse=True)
def reset_sync(tmp_path, monkeypatch):
    monkeypatch.setattr(sync_mod, "LAST_SYNC_PATH", tmp_path / "last_sync.json")
    sync_mod._sync_running.clear()
    with sync_mod._subscribers_lock:
        sync_mod._subscribers.clear()
    yield
    sync_mod._sync_running.clear()
    with sync_mod._subscribers_lock:
        sync_mod._subscribers.clear()


def _wait_for_sync_done(timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not is_sync_running():
            return
        time.sleep(0.05)


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
        _wait_for_sync_done()
    assert (tmp_path / "last_sync.json").exists()
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
        _wait_for_sync_done()
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
        _wait_for_sync_done()
    assert not is_sync_running()
