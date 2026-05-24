import os
import re
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

from starred import load_starred


def _fmt_time(dt: datetime) -> str:
    return dt.strftime("%-I:%M %p")


def _fmt_time_range(dt: datetime) -> str:
    end = dt + timedelta(minutes=1)
    return f"{_fmt_time(dt)} – {_fmt_time(end)}"


def _fmt_date_label(dt: datetime) -> str:
    return dt.strftime("%A, %B %-d")


_PLAYER_PRIORITY = ["fcamera", "ecamera", "dcamera"]


def _stitched_path(base: Path, session_name: str) -> str | None:
    """Return the best available stitched video path for the player."""
    out_dir = base.parent / "stitched"
    # Prefer higher-quality cameras
    for camera in _PLAYER_PRIORITY:
        f = out_dir / f"{session_name}--{camera}.mp4"
        if f.exists():
            return f"stitched/{f.name}"
    # Fall back to any stitched camera
    for f in sorted(out_dir.glob(f"{session_name}--*.mp4")):
        return f"stitched/{f.name}"
    return None


def _thumbnail_path(base: Path, session_name: str) -> str | None:
    out = base.parent / "stitched" / f"{session_name}.jpg"
    return f"stitched/{session_name}.jpg" if out.exists() else None


_CAMERA_LABELS = {
    "fcamera": "Front HD",
    "ecamera": "Wide HD",
    "dcamera": "Driver",
}


def _session_downloads(base: Path, session_name: str) -> list[dict]:
    out_dir = base.parent / "stitched"
    result = []
    for f in sorted(out_dir.glob(f"{session_name}--*.mp4")):
        camera = f.stem[len(session_name) + 2:]
        label = _CAMERA_LABELS.get(camera, camera)
        result.append({"label": label, "path": f"stitched/{f.name}"})
    return result


def _order_files(files: list[str]) -> list[str]:
    if "qcamera.ts" in files:
        rest = sorted(f for f in files if f != "qcamera.ts")
        return ["qcamera.ts"] + rest
    return sorted(files)


def _group_sessions_by_date(sessions: list[dict]) -> list[dict]:
    """sessions: list of dicts with 'start_dt' (datetime) + all output fields."""
    by_date: dict[str, list] = defaultdict(list)
    for s in sessions:
        date_key = s["start_dt"].strftime("%Y-%m-%d")
        by_date[date_key].append(s)

    result = []
    for date_key in sorted(by_date.keys(), reverse=True):
        day_sessions = sorted(by_date[date_key], key=lambda s: s["start_dt"], reverse=True)
        dt = day_sessions[0]["start_dt"]
        result.append({
            "date": date_key,
            "date_label": _fmt_date_label(dt),
            "sessions": [
                {k: v for k, v in s.items() if k != "start_dt"}
                for s in day_sessions
            ],
        })
    return result


def build_recording_tree(local_path: str, starred: set[str] | None = None) -> list:
    base = Path(local_path).resolve() / "realdata"
    if not base.exists():
        return []

    flat_seg_pattern = re.compile(r"^(.+)--(\d+)$")
    top_dirs = sorted(d for d in base.iterdir() if d.is_dir())

    if not top_dirs:
        return []

    if starred is None:
        starred = load_starred()

    sample = top_dirs[0]
    has_nested = any(sub.is_dir() and sub.name.isdigit() for sub in sample.iterdir())

    if has_nested:
        return _build_nested(base, top_dirs, starred)
    return _build_flat(base, top_dirs, flat_seg_pattern, starred)


def _build_flat(base: Path, top_dirs: list[Path], pattern: re.Pattern, starred: set[str]) -> list:
    groups: dict[str, list] = defaultdict(list)
    for d in top_dirs:
        m = pattern.match(d.name)
        if m:
            session_name, seg_index = m.group(1), int(m.group(2))
        else:
            session_name, seg_index = d.name, 0
        raw_files = [f.name for f in d.iterdir() if f.is_file()]
        if not raw_files:
            continue
        mtime = os.path.getmtime(d)
        groups[session_name].append((seg_index, d.name, raw_files, mtime))

    sessions = []
    for session_name, segs in groups.items():
        segs_sorted = sorted(segs, key=lambda t: t[0])
        # Start time from the --0 segment's mtime; if absent, back-calculate from earliest segment
        min_seg_index = segs_sorted[0][0]
        if min_seg_index == 0:
            start_mtime = segs_sorted[0][3]
        else:
            fallback_mtime = segs_sorted[0][3]
            start_mtime = fallback_mtime - min_seg_index * 60
        start_dt = datetime.fromtimestamp(start_mtime)
        # mtime is the best available timestamp; it may drift after filesystem operations
        segments = []
        for seg_index, folder_name, raw_files, _ in segs_sorted:
            seg_dt = start_dt + timedelta(minutes=seg_index)
            segments.append({
                "path": f"realdata/{folder_name}",
                "index": seg_index,
                "time_label": _fmt_time_range(seg_dt),
                "files": _order_files(raw_files),
            })
        max_seg_index = segs_sorted[-1][0]
        sessions.append({
            "session": session_name,
            "start_label": _fmt_time(start_dt),
            "duration_min": max_seg_index + 1,
            "segments": segments,
            "stitched_path": _stitched_path(base, session_name),
            "thumbnail_path": _thumbnail_path(base, session_name),
            "downloads": _session_downloads(base, session_name),
            "starred": session_name in starred,
            "start_dt": start_dt,
        })

    return _group_sessions_by_date(sessions)


def _build_nested(base: Path, top_dirs: list[Path], starred: set[str]) -> list:
    sessions = []
    for session_dir in top_dirs:
        seg_dirs = sorted(
            (d for d in session_dir.iterdir() if d.is_dir() and d.name.isdigit()),
            key=lambda p: int(p.name),
        )
        raw_segments = []
        for seg_dir in seg_dirs:
            raw_files = [f.name for f in seg_dir.iterdir() if f.is_file()]
            if raw_files:
                raw_segments.append((int(seg_dir.name), seg_dir, raw_files))
        if not raw_segments:
            continue

        first_seg_dir = raw_segments[0][1]
        start_dt = datetime.fromtimestamp(os.path.getmtime(first_seg_dir))
        segments = []
        for seg_index, seg_dir, raw_files in raw_segments:
            seg_dt = start_dt + timedelta(minutes=seg_index)
            segments.append({
                "path": f"realdata/{session_dir.name}/{seg_dir.name}",
                "index": seg_index,
                "time_label": _fmt_time_range(seg_dt),
                "files": _order_files(raw_files),
            })
        sessions.append({
            "session": session_dir.name,
            "start_label": _fmt_time(start_dt),
            "duration_min": len(segments),
            "segments": segments,
            "stitched_path": _stitched_path(base, session_dir.name),
            "thumbnail_path": _thumbnail_path(base, session_dir.name),
            "downloads": _session_downloads(base, session_dir.name),
            "starred": session_dir.name in starred,
            "start_dt": start_dt,
        })

    return _group_sessions_by_date(sessions)


def resolve_file_path(local_path: str, rel_path: str) -> Path | None:
    base = Path(local_path).resolve()
    target = (base / rel_path).resolve()
    if not str(target).startswith(str(base) + "/") and target != base:
        return None
    if not target.is_file():
        return None
    return target
