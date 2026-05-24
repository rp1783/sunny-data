import logging
import os
import subprocess
import tempfile
from pathlib import Path

_log = logging.getLogger(__name__)


def _concat_files(src_files: list[Path], out_file: Path, timeout: int = 600) -> bool:
    """Run ffmpeg concat on src_files → out_file. Returns True on success."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as fh:
        for f in src_files:
            fh.write(f"file '{f.resolve()}'\n")
        filelist = fh.name
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", filelist,
             "-c", "copy", str(out_file)],
            capture_output=True,
            timeout=timeout,
        )
        if result.returncode != 0:
            _log.warning("ffmpeg failed for %s: %s", out_file.name,
                         result.stderr.decode(errors="replace")[-500:])
            return False
        return True
    except Exception as exc:
        _log.warning("ffmpeg error for %s: %s", out_file.name, exc)
        return False
    finally:
        try:
            os.unlink(filelist)
        except OSError:
            pass


def _generate_thumbnail(mp4_path: Path, jpg_path: Path) -> None:
    try:
        subprocess.run(
            ["ffmpeg", "-y", "-ss", "00:00:05", "-i", str(mp4_path),
             "-vframes", "1", "-vf", "scale=480:-2", "-q:v", "4", str(jpg_path)],
            capture_output=True,
            timeout=30,
        )
    except Exception as exc:
        _log.warning("Thumbnail generation failed for %s: %s", mp4_path.name, exc)


def _needs_stitch(out_file: Path, src_files: list[Path]) -> bool:
    """Return True if out_file is missing or older than any src file."""
    if not out_file.exists():
        return True
    out_mtime = out_file.stat().st_mtime
    return any(f.stat().st_mtime > out_mtime for f in src_files)


def stitch_session(
    local_path: str,
    session_name: str,
    segment_paths: list[str],
) -> str:
    """Stitch all camera streams for a session.

    Produces:
      stitched/{session}.mp4          — qcamera.ts
      stitched/{session}--fcamera.mp4 — fcamera.hevc (if present)
      stitched/{session}--ecamera.mp4 — ecamera.hevc (if present)
      stitched/{session}.jpg          — thumbnail from main video

    Returns 'stitched', 'skipped', or 'error'.
    """
    base = Path(local_path)
    out_dir = base / "stitched"
    out_dir.mkdir(exist_ok=True)

    # ── qcamera (main video) ──────────────────────────────────────────────
    ts_files = [base / p / "qcamera.ts" for p in segment_paths]
    ts_files = [f for f in ts_files if f.exists()]

    if not ts_files:
        return "skipped"

    main_mp4 = out_dir / f"{session_name}.mp4"
    jpg_path = out_dir / f"{session_name}.jpg"
    did_stitch = False

    if _needs_stitch(main_mp4, ts_files):
        if not _concat_files(ts_files, main_mp4):
            return "error"
        did_stitch = True

    if not jpg_path.exists():
        _generate_thumbnail(main_mp4, jpg_path)

    # ── HEVC cameras ──────────────────────────────────────────────────────
    hevc_names: set[str] = set()
    for p in segment_paths:
        for f in (base / p).iterdir():
            if f.suffix == ".hevc":
                hevc_names.add(f.name)

    for hevc_name in sorted(hevc_names):
        camera = hevc_name.removesuffix(".hevc")
        src = [base / p / hevc_name for p in segment_paths]
        src = [f for f in src if f.exists()]
        if not src:
            continue
        out = out_dir / f"{session_name}--{camera}.mp4"
        if _needs_stitch(out, src):
            _concat_files(src, out)
            did_stitch = True

    return "stitched" if did_stitch else "skipped"


def stitch_all(local_path: str, on_progress=None) -> dict[str, str]:
    """Stitch all sessions found under local_path.

    Returns {session_name: 'stitched'|'skipped'|'error'}.
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
