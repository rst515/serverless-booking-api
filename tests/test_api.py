from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app import dal
from app.models import BookingCreate, BookingUpdate


class FakeTable:
    def __init__(self):
        self.items = {}

    def put_item(self, Item):  # noqa NOSONAR
        self.items[Item["booking_id"]] = Item

    def get_item(self, Key):  # noqa NOSONAR
        item = self.items.get(Key["booking_id"])
        return {"Item": item} if item else {}

    def update_item(self, **kwargs):
        key = kwargs["Key"]["booking_id"]
        attrs = self.items[key]
        # naive: apply only status or replaces values from ExpressionAttributeValues
        eav = kwargs.get("ExpressionAttributeValues") or {}
        ean = kwargs.get("ExpressionAttributeNames") or {}
        update_expr = kwargs.get("UpdateExpression", "")
        if "SET" in update_expr:
            set_part = update_expr.split("SET", 1)[1].split("REMOVE")[0]
            for assign in [s.strip() for s in set_part.split(",") if s.strip()]:
                name, val = [s.strip() for s in assign.split("=")]
                name = name.replace("#_", "")
                if name in ean:
                    name = ean[name]
                val = eav[val]
                attrs[name] = val
        if "REMOVE ttl" in update_expr and "ttl" in attrs:
            del attrs["ttl"]
        self.items[key] = attrs
        return {"Attributes": attrs}

    def delete_item(self, Key):  # noqa NOSONAR
        self.items.pop(Key["booking_id"], None)

    def query(self, **kwargs):
        uid = kwargs["ExpressionAttributeValues"][":uid"]
        items = [it for it in self.items.values() if it.get("user_id") == uid]
        return {"Items": items}


@pytest.fixture(autouse=True)
def patch_table(monkeypatch):
    fake = FakeTable()
    monkeypatch.setattr(dal, "_table", fake)
    return fake


def test_create_and_get_booking():
    now = datetime.now(UTC)
    payload = BookingCreate(
        user_id="u1",
        resource_id="r1",
        start_time=now + timedelta(hours=1),
        end_time=now + timedelta(hours=2),
        reminder_lead_seconds=900,
    )
    booking = dal.create_booking(payload)
    fetched = dal.get_booking(booking.booking_id)
    assert fetched.booking_id == booking.booking_id
    assert fetched.user_id == "u1"
    assert fetched.ttl is not None


def test_list_bookings_for_user():
    now = datetime.now(UTC)
    b1 = dal.create_booking(BookingCreate(user_id="u1", resource_id="r1", start_time=now, end_time=now))
    _ = dal.create_booking(BookingCreate(user_id="u2", resource_id="r2", start_time=now, end_time=now))
    b3 = dal.create_booking(BookingCreate(user_id="u1", resource_id="r3", start_time=now, end_time=now))
    bookings = dal.list_bookings_for_user("u1")
    ids = sorted([b.booking_id for b in bookings])
    assert ids == sorted([b1.booking_id, b3.booking_id])


def test_get_booking_not_found_raises_keyerror():
    with pytest.raises(KeyError):
        dal.get_booking("does-not-exist")


def test_update_booking_changes_fields_and_ttl_set():
    # Use fixed times to assert TTL math
    start = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
    end = start + timedelta(hours=1)
    b = dal.create_booking(
        BookingCreate(
            user_id="u-upd",
            resource_id="r-old",
            start_time=start,
            end_time=end,
            reminder_lead_seconds=1200,  # 20 min
        )
    )
    # Update: change resource and reminder lead seconds and adjust start_time and end_time to a later time
    new_start = start + timedelta(hours=2)
    new_end = end + timedelta(hours=2)
    updated = dal.update_booking(
        b.booking_id,
        BookingUpdate(
            resource_id="r-new",
            start_time=new_start,
            end_time=new_end,
            reminder_lead_seconds=600,
        ),
    )
    assert updated.resource_id == "r-new"
    assert updated.start_time == new_start
    # TTL should be start - lead (epoch seconds); just assert it is present and plausible
    assert updated.ttl is not None
    assert updated.ttl == int(new_start.timestamp()) - 600


def test_update_booking_remove_ttl_when_lead_none():
    start = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
    end = start + timedelta(hours=1)
    b = dal.create_booking(
        BookingCreate(
            user_id="u-ttl",
            resource_id="r1",
            start_time=start,
            end_time=end,
            reminder_lead_seconds=300,
        )
    )
    assert dal.get_booking(b.booking_id).ttl is not None
    # Setting reminder_lead_seconds to None removes TTL (REMOVE ttl only)
    updated = dal.update_booking(b.booking_id, BookingUpdate(reminder_lead_seconds=None))
    assert updated.ttl is None


def test_update_booking_noop_returns_current():
    start = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
    end = start + timedelta(hours=1)
    b = dal.create_booking(
        BookingCreate(
            user_id="u-noop",
            resource_id="r1",
            start_time=start,
            end_time=end,
            reminder_lead_seconds=None,  # no ttl initially
        )
    )
    # No fields provided -> returns current item unchanged
    updated = dal.update_booking(b.booking_id, BookingUpdate())
    assert updated.booking_id == b.booking_id
    assert updated.resource_id == b.resource_id
    assert updated.ttl is None


def test_cancel_booking_sets_status_cancelled():
    start = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
    end = start + timedelta(hours=1)
    b = dal.create_booking(
        BookingCreate(user_id="u-cancel", resource_id="r1", start_time=start, end_time=end)
    )
    cancelled = dal.cancel_booking(b.booking_id)
    assert cancelled.status == "cancelled"


def test_delete_booking_then_get_raises():
    start = datetime(2030, 1, 1, 12, 0, tzinfo=UTC)
    end = start + timedelta(hours=1)
    b = dal.create_booking(
        BookingCreate(user_id="u-del", resource_id="r1", start_time=start, end_time=end)
    )
    dal.delete_booking(b.booking_id)
    with pytest.raises(KeyError):
        dal.get_booking(b.booking_id)


def test_create_with_naive_datetimes_normalized_to_utc():
    # Provide naive datetimes; DAL should treat them as UTC and return tz-aware
    start = datetime(2030, 1, 1, 12, 0)  # naive
    end = start + timedelta(hours=1)
    b = dal.create_booking(
        BookingCreate(
            user_id="u-naive",
            resource_id="r1",
            start_time=start,
            end_time=end,
            reminder_lead_seconds=60,
        )
    )
    assert b.start_time.tzinfo is not None
    assert b.end_time.tzinfo is not None
