import logging
import re
import shutil
from datetime import datetime, timedelta
from pathlib import Path

_log = logging.getLogger(__name__)

_FLAT_PATTERN = re.compile(r"^(.+)--(\d+)$")


def cleanup_old_sessions(
    local_path: str,
    starred: set[str],
    max_age_days: int = 30,
) -> list[str]:
    """Delete sessions older than max_age_days that are not starred.

    Removes raw segment folders from realdata/ and all matching files
    from stitched/. Returns list of deleted session names.
    """
    base = Path(local_path)
    realdata = base / "realdata"
    stitched = base / "stitched"

    if not realdata.exists():
        return []

    cutoff = datetime.now() - timedelta(days=max_age_days)

    # Group segment dirs by session name and track the earliest mtime
    session_mtimes: dict[str, float] = {}
    session_dirs: dict[str, list[Path]] = {}

    for d in realdata.iterdir():
        if not d.is_dir():
            continue
        m = _FLAT_PATTERN.match(d.name)
        session_name = m.group(1) if m else d.name
        mtime = d.stat().st_mtime
        if session_name not in session_mtimes or mtime < session_mtimes[session_name]:
            session_mtimes[session_name] = mtime
        session_dirs.setdefault(session_name, []).append(d)

    deleted = []
    for session_name, mtime in session_mtimes.items():
        if session_name in starred:
            continue
        if datetime.fromtimestamp(mtime) >= cutoff:
            continue

        _log.info("Deleting expired session %s", session_name)
        for d in session_dirs.get(session_name, []):
            shutil.rmtree(d, ignore_errors=True)

        if stitched.exists():
            for f in stitched.glob(f"{session_name}*"):
                try:
                    f.unlink()
                except OSError:
                    pass

        deleted.append(session_name)

    return deleted
