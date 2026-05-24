import logging as _logging
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException
from log_buffer import RingBufferHandler, get_all as get_logs
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
from starred import add_star, remove_star
from stitching import stitch_all
from sync import get_last_sync, is_sync_running, run_sync, sse_generator

_log = _logging.getLogger(__name__)

_handler = RingBufferHandler()
_handler.setFormatter(_logging.Formatter("%(name)s: %(message)s"))
_logging.getLogger().addHandler(_handler)
_logging.getLogger().setLevel(_logging.INFO)

app = FastAPI()


@app.middleware("http")
async def no_cache_static(request, call_next):
    response = await call_next(request)
    if request.url.path.endswith((".js", ".css")):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


class ConfigPayload(BaseModel):
    device_ip: str
    device_user: str
    ssh_port: int
    remote_path: str
    local_path: str


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
    config = AppConfig(**payload.model_dump())
    save_config(config)
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


@app.post("/api/stitch")
def trigger_stitch():
    config = load_config()
    if not config:
        raise HTTPException(status_code=400, detail="Configuration incomplete")
    threading.Thread(
        target=stitch_all,
        args=(config.local_path,),
        daemon=True,
    ).start()
    return {"ok": True}


@app.post("/api/star/{session}")
def star_session(session: str):
    add_star(session)
    return {"ok": True}


@app.delete("/api/star/{session}")
def unstar_session(session: str):
    remove_star(session)
    return {"ok": True}


@app.get("/api/logs")
def get_log_entries():
    return get_logs()


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
