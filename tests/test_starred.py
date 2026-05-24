import json
import pytest
from pathlib import Path
from unittest.mock import patch


@pytest.fixture(autouse=True)
def isolated_starred(tmp_path):
    with patch("starred.DATA_DIR", tmp_path):
        yield tmp_path


def test_load_starred_missing_file():
    from starred import load_starred
    assert load_starred() == set()


def test_add_and_load_starred(isolated_starred):
    from starred import add_star, load_starred
    add_star("session-abc")
    assert "session-abc" in load_starred()


def test_remove_star(isolated_starred):
    from starred import add_star, remove_star, load_starred
    add_star("session-abc")
    remove_star("session-abc")
    assert "session-abc" not in load_starred()


def test_remove_star_not_present(isolated_starred):
    from starred import remove_star, load_starred
    remove_star("nonexistent")
    assert load_starred() == set()


def test_multiple_stars(isolated_starred):
    from starred import add_star, load_starred
    add_star("a")
    add_star("b")
    add_star("c")
    assert load_starred() == {"a", "b", "c"}


def test_add_star_idempotent(isolated_starred):
    from starred import add_star, load_starred
    add_star("a")
    add_star("a")
    assert load_starred() == {"a"}


def test_starred_persisted_as_json(isolated_starred):
    from starred import add_star, _path
    add_star("x")
    data = json.loads(_path().read_text())
    assert "x" in data


def test_load_starred_corrupt_file(isolated_starred):
    from starred import load_starred, _path
    _path().write_text("not-json")
    assert load_starred() == set()
