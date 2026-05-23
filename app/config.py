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
