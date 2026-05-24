import pytest
from pathlib import Path
import config as config_mod
from config import AppConfig, load_config, save_config, save_ssh_key, is_config_complete

_cfg = dict(device_ip="10.0.0.1", device_user="comma", ssh_port=22,
            remote_path="/data/", local_path="/recordings")


def test_load_config_returns_none_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path)
    assert load_config() is None


def test_save_and_load_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(config_mod, "DATA_DIR", tmp_path)
    cfg = AppConfig(**_cfg)
    save_config(cfg)
    loaded = load_config()
    assert loaded is not None
    assert loaded.device_ip == "10.0.0.1"


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
    assert not is_config_complete(AppConfig(**{**_cfg, "device_ip": ""}))


def test_is_config_complete_true_when_all_set():
    assert is_config_complete(AppConfig(**_cfg))
