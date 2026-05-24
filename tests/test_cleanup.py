import time
import pytest
from pathlib import Path
from datetime import datetime, timedelta


def _make_session(realdata: Path, name: str, age_days: float, segments: int = 1):
    """Create a flat session with the given age (mtime set accordingly)."""
    mtime = (datetime.now() - timedelta(days=age_days)).timestamp()
    for i in range(segments):
        seg = realdata / f"{name}--{i}"
        seg.mkdir(parents=True, exist_ok=True)
        (seg / "video.ts").write_bytes(b"data")
        import os
        os.utime(seg, (mtime, mtime))


def test_no_realdata_dir(tmp_path):
    from cleanup import cleanup_old_sessions
    result = cleanup_old_sessions(str(tmp_path), set())
    assert result == []


def test_old_session_deleted(tmp_path):
    from cleanup import cleanup_old_sessions
    realdata = tmp_path / "realdata"
    _make_session(realdata, "old-session", age_days=31)
    deleted = cleanup_old_sessions(str(tmp_path), set())
    assert "old-session" in deleted
    assert not (realdata / "old-session--0").exists()


def test_recent_session_kept(tmp_path):
    from cleanup import cleanup_old_sessions
    realdata = tmp_path / "realdata"
    _make_session(realdata, "new-session", age_days=5)
    deleted = cleanup_old_sessions(str(tmp_path), set())
    assert deleted == []
    assert (realdata / "new-session--0").exists()


def test_starred_session_kept(tmp_path):
    from cleanup import cleanup_old_sessions
    realdata = tmp_path / "realdata"
    _make_session(realdata, "keep-me", age_days=60)
    deleted = cleanup_old_sessions(str(tmp_path), {"keep-me"})
    assert deleted == []
    assert (realdata / "keep-me--0").exists()


def test_stitched_files_removed(tmp_path):
    from cleanup import cleanup_old_sessions
    realdata = tmp_path / "realdata"
    stitched = tmp_path / "stitched"
    stitched.mkdir()
    _make_session(realdata, "old-session", age_days=31)
    (stitched / "old-session--fcamera.mp4").write_bytes(b"mp4")
    (stitched / "old-session.jpg").write_bytes(b"jpg")
    cleanup_old_sessions(str(tmp_path), set())
    assert not (stitched / "old-session--fcamera.mp4").exists()
    assert not (stitched / "old-session.jpg").exists()


def test_multi_segment_session_all_deleted(tmp_path):
    from cleanup import cleanup_old_sessions
    realdata = tmp_path / "realdata"
    _make_session(realdata, "old-multi", age_days=45, segments=3)
    cleanup_old_sessions(str(tmp_path), set())
    for i in range(3):
        assert not (realdata / f"old-multi--{i}").exists()


def test_custom_max_age(tmp_path):
    from cleanup import cleanup_old_sessions
    realdata = tmp_path / "realdata"
    _make_session(realdata, "middle", age_days=10)
    # default 30 days: kept
    assert cleanup_old_sessions(str(tmp_path), set(), max_age_days=30) == []
    # custom 7 days: deleted
    _make_session(realdata, "middle", age_days=10)
    deleted = cleanup_old_sessions(str(tmp_path), set(), max_age_days=7)
    assert "middle" in deleted
