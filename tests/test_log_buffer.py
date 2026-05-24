import logging
import log_buffer


def setup_function():
    log_buffer._buffer.clear()


def test_append_stores_entry():
    log_buffer.append("INFO", "hello")
    entries = log_buffer.get_all()
    assert len(entries) == 1
    assert entries[0]["level"] == "INFO"
    assert entries[0]["msg"] == "hello"
    assert "ts" in entries[0]


def test_get_all_returns_in_order():
    log_buffer.append("INFO", "first")
    log_buffer.append("ERROR", "second")
    entries = log_buffer.get_all()
    assert entries[0]["msg"] == "first"
    assert entries[1]["msg"] == "second"


def test_maxlen_evicts_oldest():
    for i in range(510):
        log_buffer.append("INFO", str(i))
    entries = log_buffer.get_all()
    assert len(entries) == 500
    assert entries[0]["msg"] == "10"


def test_ring_buffer_handler_captures_log_record():
    handler = log_buffer.RingBufferHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger = logging.getLogger("test.ring")
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)

    logger.warning("test warning message")

    entries = log_buffer.get_all()
    assert any(e["level"] == "WARNING" and "test warning message" in e["msg"] for e in entries)

    logger.removeHandler(handler)
