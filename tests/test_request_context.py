# tests/test_request_context.py
from __future__ import annotations

from core.request_context import set_request_id, get_request_id, clear_request_id


def test_request_context_propagation():
    clear_request_id()
    assert get_request_id() is None
    set_request_id("req-1")
    assert get_request_id() == "req-1"
    clear_request_id()
    assert get_request_id() is None
