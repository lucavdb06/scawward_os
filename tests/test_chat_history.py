"""Round-trip tests for UI chat history serialization."""
from __future__ import annotations

import json

from backend.db.conversation_repo import messages_to_chat_events


def test_messages_to_chat_events_roundtrip() -> None:
    rows = [
        {"role": "user", "content": "hi", "id": "1", "created_at": ""},
        {
            "role": "tool",
            "content": json.dumps({"name": "read_file", "input": {"path": "/x"}, "result": {"ok": True}}),
            "id": "2",
            "created_at": "",
        },
        {"role": "assistant", "content": "done", "id": "3", "created_at": ""},
    ]
    ev = messages_to_chat_events(rows)
    assert ev[0]["type"] == "text" and "\n> hi\n" in ev[0]["data"]["text"]
    assert ev[1]["type"] == "tool"
    assert ev[1]["data"]["name"] == "read_file"
    assert ev[2]["data"]["text"] == "done"
