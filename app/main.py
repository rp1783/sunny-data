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
