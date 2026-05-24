import json
import logging
import os
import threading
from pathlib import Path

_log = logging.getLogger(__name__)

_SCHEMA_DIR = Path(__file__).parent / "schemas"
_CACHE_VERSION = 1
_M_PER_S_TO_MPH = 2.23694
_M_TO_MILES = 0.000621371

_capnp = None
_log_schema = None
_schema_lock = threading.Lock()


def _load_schema():
    global _capnp, _log_schema
    with _schema_lock:
        if _log_schema is not None:
            return _log_schema
        try:
            import capnp as _c
            _c.remove_import_hook()
            _log_schema = _c.load(str(_SCHEMA_DIR / "log.capnp"), imports=[str(_SCHEMA_DIR)])
            _capnp = _c
            return _log_schema
        except Exception as exc:
            _log.warning("Failed to load capnp schema: %s", exc)
            return None


def _parse_qlog(path: Path) -> dict:
    """Decompress qlog.zst to a temp file and iterate capnp messages."""
    import os
    import tempfile
    import zstandard as zstd

    schema = _load_schema()
    if schema is None:
        return {}

    speed_samples: list[tuple[int, float]] = []   # (logMonoTime_ns, vEgo_m_s)
    gps_points: list[tuple[float, float, float]] = []  # (lat, lon, accuracy)
    op_samples: list[tuple[int, bool]] = []         # (logMonoTime_ns, enabled)

    tmp_path = None
    try:
        dctx = zstd.ZstdDecompressor()
        fd, tmp_path = tempfile.mkstemp(suffix=".capnp")
        with os.fdopen(fd, "wb") as tmp_fh, open(path, "rb") as src_fh:
            dctx.copy_stream(src_fh, tmp_fh)

        with open(tmp_path, "rb") as fh:
            for msg in schema.Event.read_multiple(fh):
                mono = 0
                try:
                    mono = msg.logMonoTime
                except Exception:
                    pass

                which = msg.which()

                if which == "carState":
                    try:
                        speed_samples.append((mono, msg.carState.vEgo))
                    except Exception:
                        pass

                elif which == "gpsLocationExternal":
                    try:
                        g = msg.gpsLocationExternal
                        gps_points.append((g.latitude, g.longitude, g.accuracy))
                    except Exception:
                        pass

                elif which == "controlsState":
                    try:
                        op_samples.append((mono, msg.controlsState.enabled))
                    except Exception:
                        pass

    except Exception as exc:
        _log.debug("qlog parse error for %s: %s", path, exc)
    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

    return {
        "speed_samples": speed_samples,
        "gps_points": gps_points,
        "op_samples": op_samples,
    }


def _compute_stats(all_samples: list[dict]) -> dict:
    """Aggregate samples from all segments into a stats dict."""
    speed_all: list[tuple[int, float]] = []
    gps_all: list[tuple[float, float, float]] = []
    op_all: list[tuple[int, bool]] = []

    for s in all_samples:
        speed_all.extend(s.get("speed_samples", []))
        gps_all.extend(s.get("gps_points", []))
        op_all.extend(s.get("op_samples", []))

    speed_all.sort(key=lambda x: x[0])
    op_all.sort(key=lambda x: x[0])

    # Distance: integrate vEgo over time
    distance_m = 0.0
    for i in range(1, len(speed_all)):
        dt_s = (speed_all[i][0] - speed_all[i - 1][0]) / 1e9
        if 0 < dt_s < 5:  # ignore large gaps (segment boundaries)
            avg_v = (speed_all[i][1] + speed_all[i - 1][1]) / 2
            distance_m += avg_v * dt_s

    # Speed stats (exclude near-stationary)
    moving = [v for _, v in speed_all if v > 0.5]
    avg_speed_mph = (sum(moving) / len(moving) * _M_PER_S_TO_MPH) if moving else 0.0
    max_speed_mph = (max(moving) * _M_PER_S_TO_MPH) if moving else 0.0

    # OP active time and disengagements
    op_active_s = 0.0
    disengagements = 0
    prev_enabled = False
    for i in range(1, len(op_all)):
        cur_enabled = op_all[i][1]
        if prev_enabled:
            dt_s = (op_all[i][0] - op_all[i - 1][0]) / 1e9
            if 0 < dt_s < 5:
                op_active_s += dt_s
        if prev_enabled and not cur_enabled:
            disengagements += 1
        prev_enabled = cur_enabled

    # GPS route — filter to accuracy <= 10m
    good_gps = [(lat, lon) for lat, lon, acc in gps_all if acc <= 10.0]

    # Thin route_points to at most 500 points for payload size
    if len(good_gps) > 500:
        step = len(good_gps) // 500
        good_gps = good_gps[::step]

    return {
        "distance_miles": round(distance_m * _M_TO_MILES, 2),
        "avg_speed_mph": round(avg_speed_mph, 1),
        "max_speed_mph": round(max_speed_mph, 1),
        "openpilot_active_min": round(op_active_s / 60, 1),
        "disengagements": disengagements,
        "gps_start": list(good_gps[0]) if good_gps else None,
        "gps_end": list(good_gps[-1]) if good_gps else None,
        "route_points": [list(p) for p in good_gps],
    }


# ── Cache ──────────────────────────────────────────────────────────────────

from config import DATA_DIR

_CACHE_PATH = DATA_DIR / "stats_cache.json"
_cache_lock = threading.Lock()


def _load_cache() -> dict:
    if not _CACHE_PATH.exists():
        return {"version": _CACHE_VERSION, "sessions": {}}
    try:
        data = json.loads(_CACHE_PATH.read_text())
        if data.get("version") != _CACHE_VERSION:
            return {"version": _CACHE_VERSION, "sessions": {}}
        return data
    except Exception:
        return {"version": _CACHE_VERSION, "sessions": {}}


def _save_cache(cache: dict) -> None:
    try:
        _CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _CACHE_PATH.write_text(json.dumps(cache, separators=(",", ":")))
    except Exception as exc:
        _log.warning("Failed to save stats cache: %s", exc)


def _cache_key(local_path: str, segment_paths: list[str]) -> str:
    base = Path(local_path)
    total_size = 0
    max_mtime = 0.0
    count = 0
    for seg_path in segment_paths:
        qlog = base / seg_path / "qlog.zst"
        if qlog.exists():
            st = qlog.stat()
            total_size += st.st_size
            max_mtime = max(max_mtime, st.st_mtime)
            count += 1
    return f"{count}:{total_size}:{max_mtime:.3f}"


def get_or_compute_stats(local_path: str, session_name: str, segment_paths: list[str]) -> dict | None:
    key = _cache_key(local_path, segment_paths)
    with _cache_lock:
        cache = _load_cache()
        entry = cache["sessions"].get(session_name)
        if entry and entry.get("cache_key") == key:
            return entry["stats"]

    # Parse outside the lock (can be slow)
    stats = _parse_session(local_path, segment_paths)

    with _cache_lock:
        cache = _load_cache()
        cache["sessions"][session_name] = {"cache_key": key, "stats": stats}
        _save_cache(cache)

    return stats


def _parse_session(local_path: str, segment_paths: list[str]) -> dict | None:
    base = Path(local_path)
    all_samples = []
    found_any = False
    for seg_path in segment_paths:
        qlog = base / seg_path / "qlog.zst"
        if qlog.exists():
            found_any = True
            samples = _parse_qlog(qlog)
            has_data = any(samples.get(k) for k in ("speed_samples", "gps_points", "op_samples"))
            if has_data:
                all_samples.append(samples)

    if not found_any or not all_samples:
        return None
    try:
        return _compute_stats(all_samples)
    except Exception as exc:
        _log.warning("Stats computation failed for session: %s", exc)
        return None


def update_all_stats(local_path: str) -> dict[str, dict | None]:
    from recordings import build_recording_tree
    tree = build_recording_tree(local_path)
    results: dict[str, dict | None] = {}
    for group in tree:
        for session in group["sessions"]:
            name = session["session"]
            paths = [seg["path"] for seg in session["segments"]]
            results[name] = get_or_compute_stats(local_path, name, paths)
    return results
