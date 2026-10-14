import json

import pytest

from desk_lease_heartbeat.mcp import iter_messages


def _ok() -> dict[str, object]:
    return {"jsonrpc": "2.0", "id": 1, "result": {"isError": False, "content": [{"type": "text", "text": '{"ok":true}'}]}}


def test_plain_json_object() -> None:
    assert list(iter_messages(json.dumps(_ok()))) == [_ok()]


def test_sse_multiline_success_and_done() -> None:
    payload = json.dumps(_ok(), indent=2)
    data = "".join(f"data: {line}\n" for line in payload.splitlines())
    text = "event: message\n" + data + "\n" + "data: [DONE]\n\n"
    assert list(iter_messages(text)) == [_ok()]


def test_sse_no_space_after_colon_and_no_trailing_blank() -> None:
    compact = json.dumps(_ok())
    assert list(iter_messages(f"data:{compact}")) == [_ok()]


def test_sse_two_events() -> None:
    first = {"jsonrpc": "2.0", "id": 1, "result": {"content": []}}
    second = {"jsonrpc": "2.0", "id": 2, "error": {"code": -1, "message": "nope"}}
    text = f"data: {json.dumps(first)}\n\ndata: {json.dumps(second)}\n\n"
    assert list(iter_messages(text)) == [first, second]


def test_sse_without_json_raises() -> None:
    with pytest.raises((ValueError, json.JSONDecodeError)):
        list(iter_messages("event: endpoint\ndata: not-json\n\n"))
