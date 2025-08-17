from __future__ import annotations

from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.api import app
from app.models import Booking


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app)


def booking_factory(**overrides: Any) -> Booking:
    base = dict(
        booking_id="b-123",
        user_id="u-1",
        resource_id="r-1",
        start_time=datetime(2030, 1, 1, 12, 0, tzinfo=UTC),
        end_time=datetime(2030, 1, 1, 13, 0, tzinfo=UTC),
        ttl=1735689600,
        status="active",
    )
    base.update(overrides)
    return Booking(**base)


def test_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == HTTPStatus.OK
    assert resp.json() == {"status": "ok"}


def test_create_booking_route(client: TestClient) -> None:
    with patch("app.api.dal.create_booking") as mock_create:
        mock_create.return_value = booking_factory()
        payload = {
            "user_id": "u-1",
            "resource_id": "r-1",
            "start_time": datetime.now(UTC).isoformat(),
            "end_time": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "reminder_lead_seconds": 600,
        }
        resp = client.post("/bookings", json=payload)
        assert resp.status_code == HTTPStatus.CREATED
        data = resp.json()
        assert data["booking_id"] == "b-123"
        mock_create.assert_called_once()


def test_get_booking_route_found(client: TestClient) -> None:
    with patch("app.api.dal.get_booking") as mock_get:
        mock_get.return_value = booking_factory(booking_id="b-42")
        resp = client.get("/bookings/b-42")
        assert resp.status_code == HTTPStatus.OK
        assert resp.json()["booking_id"] == "b-42"


def test_get_booking_route_not_found(client: TestClient) -> None:
    with patch("app.api.dal.get_booking") as mock_get:
        mock_get.side_effect = KeyError("Booking not found")
        resp = client.get("/bookings/missing")
        assert resp.status_code == HTTPStatus.NOT_FOUND
        assert resp.json()["detail"] == "Booking not found"


def test_list_bookings_route(client: TestClient) -> None:
    with patch("app.api.dal.list_bookings_for_user") as mock_list:
        mock_list.return_value = [booking_factory(booking_id="b1"), booking_factory(booking_id="b2")]
        resp = client.get("/users/u-1/bookings")
        assert resp.status_code == HTTPStatus.OK
        ids = [b["booking_id"] for b in resp.json()]
        assert ids == ["b1", "b2"]


def test_update_booking_route_found(client: TestClient) -> None:
    with patch("app.api.dal.update_booking") as mock_update:
        mock_update.return_value = booking_factory(resource_id="r-NEW")
        resp = client.put("/bookings/b-123", json={"resource_id": "r-NEW"})
        assert resp.status_code == HTTPStatus.OK
        assert resp.json()["resource_id"] == "r-NEW"


def test_update_booking_route_not_found(client: TestClient) -> None:
    with patch("app.api.dal.update_booking") as mock_update:
        mock_update.side_effect = KeyError("Booking not found")
        resp = client.put("/bookings/missing", json={"resource_id": "x"})
        assert resp.status_code == HTTPStatus.NOT_FOUND
        assert resp.json()["detail"] == "Booking not found"


def test_delete_booking_route(client: TestClient) -> None:
    with patch("app.api.dal.delete_booking") as mock_delete:
        resp = client.delete("/bookings/b-123")
        assert resp.status_code == HTTPStatus.NO_CONTENT
        mock_delete.assert_called_once_with("b-123")


def test_cancel_booking_route(client: TestClient) -> None:
    with patch("app.api.dal.cancel_booking") as mock_cancel:
        mock_cancel.return_value = booking_factory(status="cancelled")
        resp = client.post("/bookings/b-123/cancel")
        assert resp.status_code == HTTPStatus.OK
        assert resp.json()["status"] == "cancelled"
