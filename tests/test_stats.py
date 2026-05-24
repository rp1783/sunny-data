import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "app"))

import comma_stats


# ── Fixtures ──────────────────────────────────────────────────────────────

def _make_segment_dir(base: Path, session: str, seg_idx: int, with_qlog: bool = True) -> str:
    seg_dir = base / "realdata" / f"{session}--{seg_idx}"
    seg_dir.mkdir(parents=True)
    (seg_dir / "fcamera.hevc").write_bytes(b"\x00" * 10)
    if with_qlog:
        import zstandard as zstd
        (seg_dir / "qlog.zst").write_bytes(zstd.compress(b"\x00" * 4))
    return f"realdata/{session}--{seg_idx}"


# ── Tests: missing / corrupt logs ─────────────────────────────────────────

def test_missing_qlog_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        seg_path = _make_segment_dir(Path(tmp), "sess1", 0, with_qlog=False)
        result = comma_stats.get_or_compute_stats(tmp, "sess1", [seg_path])
    assert result is None


def test_corrupt_qlog_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        seg_dir = Path(tmp) / "realdata" / "sess2--0"
        seg_dir.mkdir(parents=True)
        (seg_dir / "qlog.zst").write_bytes(b"not valid zstd data at all!!")
        result = comma_stats.get_or_compute_stats(tmp, "sess2", ["realdata/sess2--0"])
    assert result is None


def test_no_segments_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "realdata").mkdir()
        result = comma_stats.get_or_compute_stats(tmp, "sess3", [])
    assert result is None


# ── Tests: cache behaviour ────────────────────────────────────────────────

def test_cache_hit_avoids_reparse(monkeypatch):
    parse_count = [0]

    def counting_parse(path):
        parse_count[0] += 1
        return {"speed_samples": [(0, 10.0), (1_000_000_000, 10.0)], "gps_points": [], "op_samples": []}

    monkeypatch.setattr(comma_stats, "_parse_qlog", counting_parse)

    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setenv("DATA_DIR", tmp)
        # Re-point cache path into our tmp dir
        monkeypatch.setattr(comma_stats, "_CACHE_PATH", Path(tmp) / "stats_cache.json")

        seg_path = _make_segment_dir(Path(tmp), "sess4", 0)

        comma_stats.get_or_compute_stats(tmp, "sess4", [seg_path])
        comma_stats.get_or_compute_stats(tmp, "sess4", [seg_path])

    assert parse_count[0] == 1, "Should only parse once on cache hit"


def test_cache_invalidation_on_mtime_change(monkeypatch):
    parse_count = [0]

    def counting_parse(path):
        parse_count[0] += 1
        return {}

    monkeypatch.setattr(comma_stats, "_parse_qlog", counting_parse)

    with tempfile.TemporaryDirectory() as tmp:
        monkeypatch.setattr(comma_stats, "_CACHE_PATH", Path(tmp) / "stats_cache.json")

        seg_path = _make_segment_dir(Path(tmp), "sess5", 0)
        qlog = Path(tmp) / seg_path / "qlog.zst"

        comma_stats.get_or_compute_stats(tmp, "sess5", [seg_path])

        # Simulate mtime change by writing new content
        time.sleep(0.02)
        qlog.write_bytes(qlog.read_bytes() + b"\x00")
        os.utime(qlog, (time.time() + 1, time.time() + 1))

        comma_stats.get_or_compute_stats(tmp, "sess5", [seg_path])

    assert parse_count[0] == 2, "Should re-parse after mtime change"


# ── Tests: compute_stats with synthetic data ──────────────────────────────

def test_compute_stats_basic():
    # 10 m/s for 10 seconds = 100 m = 0.0621 miles
    ns = 1_000_000_000  # 1 second in nanoseconds
    speed_samples = [(i * ns, 10.0) for i in range(11)]
    op_samples = [(i * ns, True) for i in range(6)] + [(i * ns, False) for i in range(6, 11)]
    gps_points = [(37.4 + i * 0.001, -122.0 + i * 0.001, 5.0) for i in range(5)]

    samples = [{"speed_samples": speed_samples, "op_samples": op_samples, "gps_points": gps_points}]
    stats = comma_stats._compute_stats(samples)

    assert stats["distance_miles"] > 0
    assert stats["avg_speed_mph"] > 0
    assert stats["max_speed_mph"] > 0
    assert stats["openpilot_active_min"] > 0
    assert stats["disengagements"] == 1
    assert stats["gps_start"] is not None
    assert stats["gps_end"] is not None
    assert len(stats["route_points"]) == 5


def test_compute_stats_empty():
    stats = comma_stats._compute_stats([])
    assert stats["distance_miles"] == 0.0
    assert stats["disengagements"] == 0
    assert stats["gps_start"] is None


# ── Tests: API integration ─────────────────────────────────────────────────

def _make_fake_recordings_dir(tmp: str) -> None:
    session = "00000000--aabbccddee"
    seg_dir = Path(tmp) / "realdata" / f"{session}--0"
    seg_dir.mkdir(parents=True)
    (seg_dir / "fcamera.hevc").write_bytes(b"\x00" * 10)
    (seg_dir / "qcamera.ts").write_bytes(b"\x00" * 10)


def test_api_recordings_includes_stats_key(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import config as _config
    monkeypatch.setattr(_config, "DATA_DIR", tmp_path)

    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir()
    _make_fake_recordings_dir(str(recordings_dir))

    cfg = _config.AppConfig(local_path=str(recordings_dir))
    _config.save_config(cfg)

    # Patch stats to return None (no qlog)
    monkeypatch.setattr(comma_stats, "get_or_compute_stats", lambda *a, **kw: None)

    from main import app
    client = TestClient(app)
    resp = client.get("/api/recordings")
    assert resp.status_code == 200
    groups = resp.json()
    if groups:
        session = groups[0]["sessions"][0]
        assert "stats" in session
        assert session["stats"] is None


def test_api_recordings_works_when_stats_module_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    import config as _config
    monkeypatch.setattr(_config, "DATA_DIR", tmp_path)

    recordings_dir = tmp_path / "recordings"
    recordings_dir.mkdir()
    _make_fake_recordings_dir(str(recordings_dir))

    cfg = _config.AppConfig(local_path=str(recordings_dir))
    _config.save_config(cfg)

    def boom(*a, **kw):
        raise RuntimeError("stats module exploded")

    monkeypatch.setattr(comma_stats, "get_or_compute_stats", boom)

    import recordings as rec_module
    monkeypatch.setattr(rec_module, "_safe_get_stats", lambda *a, **kw: None)

    from main import app
    client = TestClient(app)
    resp = client.get("/api/recordings")
    assert resp.status_code == 200
