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


_base_payload = {
    "device_ip": "10.0.0.1", "device_user": "comma", "ssh_port": 22,
    "remote_path": "/data/", "local_path": "/recordings",
}


def test_get_config_empty_before_setup(client):
    res = client.get("/api/config")
    assert res.status_code == 200
    assert res.json() == {}


def test_post_and_get_config_roundtrip(client):
    res = client.post("/api/config", json=_base_payload)
    assert res.status_code == 200
    assert res.json() == {"ok": True}
    res2 = client.get("/api/config")
    assert res2.json()["device_ip"] == "10.0.0.1"


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
    assert res.json()["running"] is False


def test_get_recordings_empty_when_no_config(client):
    res = client.get("/api/recordings")
    assert res.status_code == 200
    assert res.json() == []


def test_serve_file_returns_404_for_missing_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path)
    client.post("/api/config", json={**_base_payload, "local_path": str(tmp_path)})
    res = client.get("/files/realdata/nosession/0/qcamera.ts")
    assert res.status_code == 404


def test_serve_file_blocks_path_traversal(client, tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path)
    client.post("/api/config", json={**_base_payload, "local_path": str(tmp_path)})
    res = client.get("/files/../etc/passwd")
    assert res.status_code in (404, 403, 422)
