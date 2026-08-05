# tests/test_core_responses.py
from __future__ import annotations

from core.responses import success_response, error_response


def test_success_response_shape():
    env = success_response(request_id="abc", data={"x": 1})
    assert env["success"] is True
    assert env["requestId"] == "abc"
    assert "timestamp" in env
    assert env["data"]["x"] == 1


def test_error_response_shape():
    env = error_response(request_id="abc", code="ERR", message="msg")
    assert env["success"] is False
    assert env["requestId"] == "abc"
    assert env["error"]["code"] == "ERR"
