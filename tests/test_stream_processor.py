from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock

import pytest

import app.stream_processor as sp


def make_ddb_attr_s(val: str) -> dict[str, Any]:
    return {"S": val}


def make_ddb_attr_n(val: int) -> dict[str, Any]:
    return {"N": str(val)}


def test_stream_processor_emits_event_for_ttl_remove(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_events = MagicMock()
    monkeypatch.setattr(sp, "_events", fake_events)

    event = {
        "Records": [
            {
                "eventName": "REMOVE",
                "dynamodb": {
                    "OldImage": {
                        "booking_id": make_ddb_attr_s("b-1"),
                        "user_id": make_ddb_attr_s("u-1"),
                        "ttl": make_ddb_attr_n(1700000000),
                    }
                },
            }
        ]
    }

    sp.lambda_handler(event, context=MagicMock())  # type: ignore[arg-type]
    assert fake_events.put_events.called
    args, kwargs = fake_events.put_events.call_args
    entry = kwargs["Entries"][0]
    assert entry["Source"] == "booking.reminder"
    assert entry["DetailType"] == "ReminderDue"
    detail = json.loads(entry["Detail"])
    assert detail["booking_id"] == "b-1"
    assert detail["user_id"] == "u-1"
    assert detail["ttl"] == 1700000000  # noqa: PLR2004


def test_stream_processor_skips_non_remove(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_events = MagicMock()
    monkeypatch.setattr(sp, "_events", fake_events)

    event = {"Records": [{"eventName": "INSERT"}]}
    sp.lambda_handler(event, context=MagicMock())  # type: ignore[arg-type]
    fake_events.put_events.assert_not_called()


def test_stream_processor_skips_missing_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    fake_events = MagicMock()
    monkeypatch.setattr(sp, "_events", fake_events)

    # Missing ttl
    event = {
        "Records": [
            {
                "eventName": "REMOVE",
                "dynamodb": {"OldImage": {"booking_id": make_ddb_attr_s("b-1"), "user_id": make_ddb_attr_s("u-1")}},
            }
        ]
    }
    sp.lambda_handler(event, context=MagicMock())  # type: ignore[arg-type]
    fake_events.put_events.assert_not_called()
