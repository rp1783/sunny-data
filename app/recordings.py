import re
from pathlib import Path


def build_recording_tree(local_path: str) -> list:
    base = Path(local_path).resolve() / "realdata"
    if not base.exists():
        return []

    # Detect layout: nested (session/segN/files) vs flat (session--segN/files)
    flat_seg_pattern = re.compile(r"^(.+)--(\d+)$")
    top_dirs = sorted(d for d in base.iterdir() if d.is_dir())

    if not top_dirs:
        return []

    # Check if any top-level dir has numeric subdirectories (nested layout)
    sample = top_dirs[0]
    has_nested = any(
        sub.is_dir() and sub.name.isdigit() for sub in sample.iterdir()
    )

    if has_nested:
        # Nested layout: session_dir/segment_N/files
        sessions = []
        for session_dir in top_dirs:
            segments = []
            for seg_dir in sorted(
                session_dir.iterdir(),
                key=lambda p: int(p.name) if p.name.isdigit() else p.name,
            ):
                if not seg_dir.is_dir():
                    continue
                files = sorted(f.name for f in seg_dir.iterdir() if f.is_file())
                if files:
                    segments.append({
                        "segment": seg_dir.name,
                        "path": f"realdata/{session_dir.name}/{seg_dir.name}",
                        "files": files,
                    })
            if segments:
                sessions.append({"session": session_dir.name, "segments": segments})
        return sessions

    # Flat layout: routeId--segN/files  →  group into sessions by prefix
    groups: dict[str, list] = {}
    for d in top_dirs:
        m = flat_seg_pattern.match(d.name)
        if m:
            session_name, seg_num = m.group(1), int(m.group(2))
        else:
            session_name, seg_num = d.name, 0
        files = sorted(f.name for f in d.iterdir() if f.is_file())
        if files:
            groups.setdefault(session_name, []).append(
                (seg_num, d.name, files)
            )

    sessions = []
    for session_name in sorted(groups):
        segs = sorted(groups[session_name], key=lambda t: t[0])
        segments = [
            {
                "segment": folder_name,
                "path": f"realdata/{folder_name}",
                "files": files,
            }
            for _, folder_name, files in segs
        ]
        sessions.append({"session": session_name, "segments": segments})

    return sessions


def resolve_file_path(local_path: str, rel_path: str) -> Path | None:
    base = Path(local_path).resolve()
    target = (base / rel_path).resolve()
    if not str(target).startswith(str(base) + "/") and target != base:
        return None
    if not target.is_file():
        return None
    return target
