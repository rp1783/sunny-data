from pathlib import Path
from recordings import build_recording_tree, resolve_file_path


def _make_segment(base: Path, session: str, segment: str, files: list[str]) -> None:
    seg_dir = base / "realdata" / session / segment
    seg_dir.mkdir(parents=True)
    for f in files:
        (seg_dir / f).write_text("data")


def test_build_tree_empty_when_no_realdata_dir(tmp_path):
    assert build_recording_tree(str(tmp_path)) == []


def test_build_tree_single_session_single_segment(tmp_path):
    _make_segment(tmp_path, "2024-11-15--08-32-10", "0", ["qcamera.ts", "fcamera.hevc", "rlog.bz2"])
    result = build_recording_tree(str(tmp_path))
    assert len(result) == 1
    assert result[0]["session"] == "2024-11-15--08-32-10"
    assert len(result[0]["segments"]) == 1
    assert result[0]["segments"][0]["segment"] == "0"
    assert set(result[0]["segments"][0]["files"]) == {"qcamera.ts", "fcamera.hevc", "rlog.bz2"}


def test_build_tree_multiple_segments_sorted(tmp_path):
    for seg in ["2", "0", "1"]:
        _make_segment(tmp_path, "2024-11-15--08-32-10", seg, ["qcamera.ts"])
    result = build_recording_tree(str(tmp_path))
    segments = [s["segment"] for s in result[0]["segments"]]
    assert segments == ["0", "1", "2"]


def test_build_tree_skips_empty_segments(tmp_path):
    (tmp_path / "realdata" / "2024-11-15--08-32-10" / "0").mkdir(parents=True)
    result = build_recording_tree(str(tmp_path))
    assert result == []


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
