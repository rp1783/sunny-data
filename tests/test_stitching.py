import os
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from stitching import stitch_all, stitch_session


def _make_seg(base: Path, folder: str, files: list[str]) -> Path:
    seg = base / "realdata" / folder
    seg.mkdir(parents=True)
    for f in files:
        (seg / f).write_text("data")
    return seg


# ── stitch_session ─────────────────────────────────────────────────────────

def test_stitch_session_runs_ffmpeg(tmp_path):
    _make_seg(tmp_path, "abc--def--0", ["fcamera.hevc"])
    _make_seg(tmp_path, "abc--def--1", ["fcamera.hevc"])

    with patch("stitching.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = stitch_session(str(tmp_path), "abc--def", [
            "realdata/abc--def--0",
            "realdata/abc--def--1",
        ])

    assert result == "stitched"
    stitch_call = mock_run.call_args_list[0][0][0]
    assert "ffmpeg" in stitch_call
    assert "-f" in stitch_call and "concat" in stitch_call
    assert str(tmp_path / "stitched" / "abc--def--fcamera.mp4") in stitch_call


def test_stitch_session_creates_stitched_dir(tmp_path):
    _make_seg(tmp_path, "abc--def--0", ["fcamera.hevc"])

    with patch("stitching.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        stitch_session(str(tmp_path), "abc--def", ["realdata/abc--def--0"])

    assert (tmp_path / "stitched").is_dir()


def _write_faststart_mp4(path: Path) -> None:
    """Write a minimal MP4 with moov before mdat so _has_faststart returns True."""
    moov = b"\x00\x00\x00\x08moov"
    mdat = b"\x00\x00\x00\x08mdat"
    path.write_bytes(moov + mdat)


def test_stitch_session_skips_when_output_newer(tmp_path):
    seg = _make_seg(tmp_path, "abc--def--0", ["fcamera.hevc"])
    out_dir = tmp_path / "stitched"
    out_dir.mkdir()
    out = out_dir / "abc--def--fcamera.mp4"
    _write_faststart_mp4(out)
    (out_dir / "abc--def.jpg").write_text("jpg")
    future = time.time() + 3600
    os.utime(out, (future, future))
    os.utime(seg, (future - 7200, future - 7200))

    with patch("stitching.subprocess.run") as mock_run:
        result = stitch_session(str(tmp_path), "abc--def", ["realdata/abc--def--0"])

    assert result == "skipped"
    assert not mock_run.called


def test_stitch_session_skips_when_no_hevc(tmp_path):
    _make_seg(tmp_path, "abc--def--0", ["qcamera.ts", "rlog.zst"])

    with patch("stitching.subprocess.run") as mock_run:
        result = stitch_session(str(tmp_path), "abc--def", ["realdata/abc--def--0"])

    assert result == "skipped"
    assert not mock_run.called


def test_stitch_session_returns_error_on_ffmpeg_failure(tmp_path):
    _make_seg(tmp_path, "abc--def--0", ["fcamera.hevc"])

    with patch("stitching.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr=b"some error")
        result = stitch_session(str(tmp_path), "abc--def", ["realdata/abc--def--0"])

    assert result == "error"


# ── stitch_all ─────────────────────────────────────────────────────────────

def _make_flat_seg(base: Path, folder: str, files: list[str], mtime: float | None = None) -> Path:
    seg = base / "realdata" / folder
    seg.mkdir(parents=True)
    for f in files:
        (seg / f).write_text("data")
    if mtime is not None:
        os.utime(seg, (mtime, mtime))
    return seg


def test_stitch_all_stitches_each_session(tmp_path):
    import time as _time
    t0 = _time.mktime(_time.strptime("2026-05-22 10:00:00", "%Y-%m-%d %H:%M:%S"))
    _make_flat_seg(tmp_path, "aaa--bbb--0", ["fcamera.hevc"], mtime=t0)
    _make_flat_seg(tmp_path, "ccc--ddd--0", ["fcamera.hevc"], mtime=t0)

    with patch("stitching.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        results = stitch_all(str(tmp_path))

    assert "aaa--bbb" in results
    assert "ccc--ddd" in results
    # 2 sessions × 1 stitch call each (thumbnail skipped: mock doesn't create files)
    assert mock_run.call_count == 2


def test_stitch_all_calls_on_progress(tmp_path):
    import time as _time
    t0 = _time.mktime(_time.strptime("2026-05-22 10:00:00", "%Y-%m-%d %H:%M:%S"))
    _make_flat_seg(tmp_path, "aaa--bbb--0", ["fcamera.hevc"], mtime=t0)

    messages = []
    with patch("stitching.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        stitch_all(str(tmp_path), on_progress=messages.append)

    assert any("aaa--bbb" in m for m in messages)


def test_stitch_all_empty_dir_returns_empty(tmp_path):
    results = stitch_all(str(tmp_path))
    assert results == {}
