import json
from config import DATA_DIR


def _path():
    return DATA_DIR / "starred.json"


def load_starred() -> set[str]:
    p = _path()
    if not p.exists():
        return set()
    try:
        return set(json.loads(p.read_text()))
    except Exception:
        return set()


def save_starred(starred: set[str]) -> None:
    p = _path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(sorted(starred), indent=2))


def add_star(session: str) -> None:
    s = load_starred()
    s.add(session)
    save_starred(s)


def remove_star(session: str) -> None:
    s = load_starred()
    s.discard(session)
    save_starred(s)
