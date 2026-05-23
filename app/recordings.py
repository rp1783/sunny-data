from pathlib import Path


def build_recording_tree(local_path: str) -> list:
    base = Path(local_path) / "realdata"
    if not base.exists():
        return []

    sessions = []
    for session_dir in sorted(base.iterdir()):
        if not session_dir.is_dir():
            continue
        segments = []
        for seg_dir in sorted(
            session_dir.iterdir(),
            key=lambda p: int(p.name) if p.name.isdigit() else p.name,
        ):
            if not seg_dir.is_dir():
                continue
            files = sorted(f.name for f in seg_dir.iterdir() if f.is_file())
            if files:
                segments.append({"segment": seg_dir.name, "files": files})
        if segments:
            sessions.append({"session": session_dir.name, "segments": segments})

    return sessions


def resolve_file_path(local_path: str, rel_path: str) -> Path | None:
    base = Path(local_path).resolve()
    target = (base / rel_path).resolve()
    if not str(target).startswith(str(base) + "/") and target != base:
        return None
    if not target.is_file():
        return None
    return target
