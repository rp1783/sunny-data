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
