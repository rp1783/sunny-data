import logging
import os
import subprocess
import tempfile
from pathlib import Path

_log = logging.getLogger(__name__)


def stitch_session(
    local_path: str,
    session_name: str,
    segment_paths: list[str],
) -> str:
    """Stitch qcamera.ts segments into a single MP4.

    Returns 'stitched', 'skipped', or 'error'.
    segment_paths: ordered relative paths like ['realdata/abc--def--0', ...].
    """
    base = Path(local_path)
    out_dir = base / "stitched"
    out_dir.mkdir(exist_ok=True)
    out_file = out_dir / f"{session_name}.mp4"

    ts_files = [base / p / "qcamera.ts" for p in segment_paths]
    ts_files = [f for f in ts_files if f.exists()]

    if not ts_files:
        return "skipped"

    if out_file.exists():
        out_mtime = out_file.stat().st_mtime
        if all(out_mtime > f.stat().st_mtime for f in ts_files):
            return "skipped"

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as fh:
        for ts in ts_files:
            fh.write(f"file '{ts.resolve()}'\n")
        filelist = fh.name

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", filelist,
                "-c", "copy",
                str(out_file),
            ],
            capture_output=True,
            timeout=600,
        )
        if result.returncode != 0:
            _log.warning(
                "ffmpeg failed for %s: %s",
                session_name,
                result.stderr.decode(errors="replace")[-500:],
            )
            return "error"
        return "stitched"
    except Exception as exc:
        _log.warning("stitch_session failed for %s: %s", session_name, exc)
        return "error"
    finally:
        try:
            os.unlink(filelist)
        except OSError:
            pass


def stitch_all(local_path: str, on_progress=None) -> dict[str, str]:
    """Stitch all sessions found under local_path.

    Returns {session_name: 'stitched'|'skipped'|'error'}.
    on_progress: optional callable(message: str) for progress reporting.
    """
    from recordings import build_recording_tree

    tree = build_recording_tree(local_path)
    results: dict[str, str] = {}
    for group in tree:
        for session in group["sessions"]:
            name = session["session"]
            paths = [seg["path"] for seg in session["segments"]]
            if on_progress:
                on_progress(f"Stitching {name}...")
            outcome = stitch_session(local_path, name, paths)
            results[name] = outcome
            if on_progress and outcome != "skipped":
                on_progress(f"  → {outcome}")
    return results
