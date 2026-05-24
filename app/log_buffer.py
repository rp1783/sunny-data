import collections
import logging
import threading
from datetime import datetime

_lock = threading.Lock()
_buffer: collections.deque = collections.deque(maxlen=500)


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append(level: str, msg: str) -> None:
    with _lock:
        _buffer.append({"ts": _now(), "level": level, "msg": msg})


def get_all() -> list[dict]:
    with _lock:
        return list(_buffer)


class RingBufferHandler(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        try:
            append(record.levelname, self.format(record))
        except Exception:
            pass
