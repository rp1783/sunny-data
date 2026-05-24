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
             "-c", "copy", "-movflags", "+faststart", str(out_file)],
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


def _has_faststart(mp4: Path) -> bool:
    """Return True if the moov atom appears before the mdat atom."""
    try:
        with mp4.open("rb") as fh:
            while True:
                size_bytes = fh.read(4)
                if len(size_bytes) < 4:
                    return False
                size = int.from_bytes(size_bytes, "big")
                name = fh.read(4)
                if name == b"moov":
                    return True
                if name == b"mdat":
                    return False
                if size < 8:
                    return False
                fh.seek(size - 8, 1)
    except OSError:
        return False


def _needs_stitch(out_file: Path, src_files: list[Path]) -> bool:
    if not out_file.exists():
        return True
    if not _has_faststart(out_file):
        return True
    out_mtime = out_file.stat().st_mtime
    return any(f.stat().st_mtime > out_mtime for f in src_files)


# Preferred camera order for thumbnail selection
_THUMB_PRIORITY = ["fcamera", "ecamera", "dcamera"]


def stitch_session(
    local_path: str,
    session_name: str,
    segment_paths: list[str],
) -> str:
    """Stitch all HEVC camera streams for a session.

    Produces stitched/{session}--{camera}.mp4 for each HEVC stream found,
    plus stitched/{session}.jpg thumbnail (from fcamera if available).

    Returns 'stitched', 'skipped', or 'error'.
    """
    base = Path(local_path)
    out_dir = base / "stitched"
    out_dir.mkdir(exist_ok=True)

    # Discover all HEVC camera streams present across segments
    hevc_names: set[str] = set()
    for p in segment_paths:
        for f in (base / p).iterdir():
            if f.suffix == ".hevc":
                hevc_names.add(f.name)

    if not hevc_names:
        return "skipped"

    did_stitch = False
    had_error = False
    stitched_cameras: dict[str, Path] = {}

    for hevc_name in sorted(hevc_names):
        camera = hevc_name.removesuffix(".hevc")
        src = [base / p / hevc_name for p in segment_paths]
        src = [f for f in src if f.exists()]
        if not src:
            continue
        out = out_dir / f"{session_name}--{camera}.mp4"
        if _needs_stitch(out, src):
            if _concat_files(src, out):
                did_stitch = True
            else:
                had_error = True
        if out.exists():
            stitched_cameras[camera] = out

    if had_error and not did_stitch:
        return "error"

    # Thumbnail from the highest-priority available camera
    jpg_path = out_dir / f"{session_name}.jpg"
    if not jpg_path.exists() and stitched_cameras:
        thumb_src = next(
            (stitched_cameras[c] for c in _THUMB_PRIORITY if c in stitched_cameras),
            next(iter(stitched_cameras.values())),
        )
        _generate_thumbnail(thumb_src, jpg_path)

    return "stitched" if did_stitch else "skipped"


def stitch_all(local_path: str, on_progress=None) -> dict[str, str]:
    """Stitch all sessions found under local_path."""
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
