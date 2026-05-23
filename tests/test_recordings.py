import os
import time
from pathlib import Path
from recordings import build_recording_tree, resolve_file_path


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_flat_seg(base: Path, folder: str, files: list[str], mtime: float | None = None) -> Path:
    """Create a flat-layout segment folder (routeId--segN/files)."""
    seg_dir = base / "realdata" / folder
    seg_dir.mkdir(parents=True)
    for f in files:
        (seg_dir / f).write_text("data")
    if mtime is not None:
        os.utime(seg_dir, (mtime, mtime))
    return seg_dir


def _make_nested_seg(base: Path, session: str, segment: str, files: list[str], mtime: float | None = None) -> Path:
    """Create a nested-layout segment folder (session/segN/files)."""
    seg_dir = base / "realdata" / session / segment
    seg_dir.mkdir(parents=True)
    for f in files:
        (seg_dir / f).write_text("data")
    if mtime is not None:
        os.utime(seg_dir, (mtime, mtime))
    return seg_dir


# ── Empty / missing ────────────────────────────────────────────────────────

def test_build_tree_empty_when_no_realdata_dir(tmp_path):
    assert build_recording_tree(str(tmp_path)) == []


def test_build_tree_empty_when_no_dirs(tmp_path):
    (tmp_path / "realdata").mkdir()
    assert build_recording_tree(str(tmp_path)) == []


# ── Flat layout ────────────────────────────────────────────────────────────

def test_flat_single_session_returns_one_date_group(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    _make_flat_seg(tmp_path, "abc--def--0", ["qcamera.ts", "fcamera.hevc"], mtime=t0)
    result = build_recording_tree(str(tmp_path))
    assert len(result) == 1
    assert result[0]["date"] == "2026-05-22"
    assert "May 22" in result[0]["date_label"]
    assert len(result[0]["sessions"]) == 1


def test_flat_session_has_start_label_and_duration(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    t1 = t0 + 60
    _make_flat_seg(tmp_path, "abc--def--0", ["qcamera.ts"], mtime=t0)
    _make_flat_seg(tmp_path, "abc--def--1", ["qcamera.ts"], mtime=t1)
    result = build_recording_tree(str(tmp_path))
    session = result[0]["sessions"][0]
    assert session["duration_min"] == 2
    assert ":" in session["start_label"]   # has time formatting


def test_flat_segment_has_index_and_time_label(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    _make_flat_seg(tmp_path, "abc--def--0", ["qcamera.ts"], mtime=t0)
    _make_flat_seg(tmp_path, "abc--def--1", ["qcamera.ts"], mtime=t0 + 60)
    result = build_recording_tree(str(tmp_path))
    segs = result[0]["sessions"][0]["segments"]
    assert segs[0]["index"] == 0
    assert segs[1]["index"] == 1
    assert "–" in segs[0]["time_label"]


def test_flat_file_ordering_qcamera_first(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    _make_flat_seg(tmp_path, "abc--def--0", ["rlog.zst", "qcamera.ts", "fcamera.hevc"], mtime=t0)
    result = build_recording_tree(str(tmp_path))
    files = result[0]["sessions"][0]["segments"][0]["files"]
    assert files[0] == "qcamera.ts"
    assert files[1:] == sorted(["rlog.zst", "fcamera.hevc"])


def test_flat_segments_sorted_by_index(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    for i in [2, 0, 1]:
        _make_flat_seg(tmp_path, f"abc--def--{i}", ["qcamera.ts"], mtime=t0 + i * 60)
    result = build_recording_tree(str(tmp_path))
    segs = result[0]["sessions"][0]["segments"]
    assert [s["index"] for s in segs] == [0, 1, 2]


def test_flat_skips_empty_segment_folders(tmp_path):
    (tmp_path / "realdata" / "abc--def--0").mkdir(parents=True)
    result = build_recording_tree(str(tmp_path))
    assert result == []


# ── Date grouping ──────────────────────────────────────────────────────────

def test_sessions_on_different_dates_get_separate_groups(tmp_path):
    t_may22 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    t_may23 = time.mktime(time.strptime("2026-05-23 10:00:00", "%Y-%m-%d %H:%M:%S"))
    _make_flat_seg(tmp_path, "aaa--bbb--0", ["qcamera.ts"], mtime=t_may22)
    _make_flat_seg(tmp_path, "ccc--ddd--0", ["qcamera.ts"], mtime=t_may23)
    result = build_recording_tree(str(tmp_path))
    assert len(result) == 2
    dates = [g["date"] for g in result]
    assert "2026-05-23" in dates
    assert "2026-05-22" in dates
    # Newest date first
    assert result[0]["date"] == "2026-05-23"


def test_sessions_within_date_sorted_newest_first(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    t1 = time.mktime(time.strptime("2026-05-22 20:00:00", "%Y-%m-%d %H:%M:%S"))
    _make_flat_seg(tmp_path, "aaa--bbb--0", ["qcamera.ts"], mtime=t0)
    _make_flat_seg(tmp_path, "ccc--ddd--0", ["qcamera.ts"], mtime=t1)
    result = build_recording_tree(str(tmp_path))
    sessions = result[0]["sessions"]
    assert sessions[0]["start_label"] != sessions[1]["start_label"]
    # The later session (t1 = 20:00) should be first
    assert sessions[0]["session"] == "ccc--ddd"


# ── Nested layout (legacy) ─────────────────────────────────────────────────

def test_nested_single_session_returns_date_group(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    _make_nested_seg(tmp_path, "2024-11-15--08-32-10", "0", ["qcamera.ts", "fcamera.hevc"], mtime=t0)
    result = build_recording_tree(str(tmp_path))
    assert len(result) == 1
    assert result[0]["date"] == "2026-05-22"
    session = result[0]["sessions"][0]
    assert session["session"] == "2024-11-15--08-32-10"
    assert session["duration_min"] == 1


def test_nested_multiple_segments_sorted(tmp_path):
    t0 = time.mktime(time.strptime("2026-05-22 19:03:00", "%Y-%m-%d %H:%M:%S"))
    for i, seg in enumerate(["2", "0", "1"]):
        _make_nested_seg(tmp_path, "2024-11-15--08-32-10", seg, ["qcamera.ts"], mtime=t0 + int(seg) * 60)
    result = build_recording_tree(str(tmp_path))
    segs = result[0]["sessions"][0]["segments"]
    assert [s["index"] for s in segs] == [0, 1, 2]


def test_nested_skips_empty_segments(tmp_path):
    (tmp_path / "realdata" / "2024-11-15--08-32-10" / "0").mkdir(parents=True)
    result = build_recording_tree(str(tmp_path))
    assert result == []


# ── resolve_file_path (unchanged) ─────────────────────────────────────────

def test_resolve_file_path_valid(tmp_path):
    f = tmp_path / "realdata" / "sess" / "0" / "qcamera.ts"
    f.parent.mkdir(parents=True)
    f.write_text("data")
    result = resolve_file_path(str(tmp_path), "realdata/sess/0/qcamera.ts")
    assert result == f


def test_resolve_file_path_blocks_traversal(tmp_path):
    assert resolve_file_path(str(tmp_path), "../etc/passwd") is None


def test_resolve_file_path_returns_none_for_missing_file(tmp_path):
    assert resolve_file_path(str(tmp_path), "realdata/nonexistent.ts") is None
