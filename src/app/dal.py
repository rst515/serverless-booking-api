from __future__ import annotations

import os
import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, TypedDict, cast

import boto3
from aws_lambda_powertools import Logger

if TYPE_CHECKING:
    # Only for static type checking; not imported at runtime
    from mypy_boto3_dynamodb.service_resource import DynamoDBServiceResource
    from mypy_boto3_dynamodb.service_resource import Table as DynamoDBTable
else:
    # Fallbacks to satisfy annotations at runtime
    DynamoDBServiceResource = Any  # type: ignore[assignment]
    DynamoDBTable = Any  # type: ignore[assignment]

from .models import Booking, BookingCreate, BookingUpdate

logger = Logger()
_TABLE_NAME = os.environ.get("TABLE_NAME", "bookings")

_dynamodb: DynamoDBServiceResource = boto3.resource("dynamodb")
_table: DynamoDBTable = _dynamodb.Table(_TABLE_NAME)

BOOKING_NOT_FOUND = "Booking not found"


class BookingItem(TypedDict, total=False):
    booking_id: str
    user_id: str
    resource_id: str
    start_time: str
    end_time: str
    ttl: int
    status: str


def _dt_to_iso(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def _iso_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s)


def _compute_ttl_from_reminder(start_time: datetime, lead_seconds: int | None) -> int | None:
    if lead_seconds is None:
        return None
    if start_time.tzinfo is None:
        start_time = start_time.replace(tzinfo=UTC)
    reminder_at = start_time.astimezone(UTC).timestamp() - lead_seconds
    # DynamoDB TTL expects epoch seconds
    return max(0, int(reminder_at))


def create_booking(payload: BookingCreate) -> Booking:
    booking_id = str(uuid.uuid4())
    ttl = _compute_ttl_from_reminder(payload.start_time, payload.reminder_lead_seconds)
    item: BookingItem = {
        "booking_id": booking_id,
        "user_id": payload.user_id,
        "resource_id": payload.resource_id,
        "start_time": _dt_to_iso(payload.start_time),
        "end_time": _dt_to_iso(payload.end_time),
        "status": "active",
    }
    if ttl is not None:
        item["ttl"] = ttl

    logger.info("Creating booking", extra={"booking_id": booking_id, "ttl": ttl})
    _table.put_item(Item=item)  # type: ignore
    return get_booking(booking_id)


def get_booking(booking_id: str) -> Booking:
    resp = cast(dict[str, Any], _table.get_item(Key={"booking_id": booking_id}))
    item = resp.get("Item")
    if not isinstance(item, dict):
        raise KeyError(BOOKING_NOT_FOUND)
    return _to_model(cast(BookingItem, item))


def list_bookings_for_user(user_id: str) -> list[Booking]:
    resp = cast(
        dict[str, Any],
        _table.query(
            IndexName="user_id_index",
            KeyConditionExpression="user_id = :uid",
            ExpressionAttributeValues={":uid": user_id},
        ),
    )
    raw_items = resp.get("Items", [])
    items: list[BookingItem] = [cast(BookingItem, it) for it in raw_items if isinstance(it, dict)]
    return [_to_model(it) for it in items]


def update_booking(booking_id: str, payload: BookingUpdate) -> Booking:
    # Fetch existing, then update selectively
    current = get_booking(booking_id)
    new_start = payload.start_time or current.start_time

    # Determine TTL behavior
    if "reminder_lead_seconds" in payload.model_fields_set:
        ttl = (
            None if payload.reminder_lead_seconds is None
            else _compute_ttl_from_reminder(new_start, payload.reminder_lead_seconds)
        )
    else:
        preserved_lead = (
            None if current.ttl is None
            else max(0, int(current.start_time.timestamp()) - current.ttl)
        )
        ttl = _compute_ttl_from_reminder(new_start, preserved_lead)

    # Build update expression
    set_parts: list[str] = []
    names: dict[str, str] = {}
    values: dict[str, Any] = {}
    remove_ttl = ttl is None

    def set_attr(name: str, value: Any) -> None:
        names[f"#_{name}"] = name
        values[f":{name}"] = value
        set_parts.append(f"#_{name} = :{name}")

    if payload.resource_id is not None:
        set_attr("resource_id", payload.resource_id)
    if payload.start_time is not None:
        set_attr("start_time", _dt_to_iso(payload.start_time))
    if payload.end_time is not None:
        set_attr("end_time", _dt_to_iso(payload.end_time))
    if not remove_ttl:
        set_attr("ttl", ttl)

    # Join parts into a single expression; if none -> no-op
    update_expr = " ".join(
        part
        for part in (
            ("SET " + ", ".join(set_parts)) if set_parts else "",
            "REMOVE ttl" if remove_ttl else "",
        )
        if part
    )

    resp = cast(
        dict[str, Any],
        _table.update_item(
            Key={"booking_id": booking_id},
            UpdateExpression=update_expr,
            ReturnValues="ALL_NEW",
            ConditionExpression="attribute_exists(booking_id)",
            ExpressionAttributeNames=names if names else None,  # type: ignore[arg-type]
            ExpressionAttributeValues=values if values else None,  # type: ignore[arg-type]
        ),
    )
    attrs = cast(dict[str, Any], resp.get("Attributes") or {})
    return _to_model(cast(BookingItem, attrs))


def delete_booking(booking_id: str) -> None:
    _table.delete_item(Key={"booking_id": booking_id})


def cancel_booking(booking_id: str) -> Booking:
    resp = cast(
        dict[str, Any],
        _table.update_item(
            Key={"booking_id": booking_id},
            UpdateExpression="SET #s = :s",
            ExpressionAttributeNames={"#s": "status"},
            ExpressionAttributeValues={":s": "cancelled"},
            ReturnValues="ALL_NEW",
        ),
    )
    attrs = cast(dict[str, Any], resp.get("Attributes") or {})
    return _to_model(cast(BookingItem, attrs))


def _to_model(item: BookingItem) -> Booking:
    return Booking(
        booking_id=item["booking_id"],
        user_id=item["user_id"],
        resource_id=item["resource_id"],
        start_time=_iso_to_dt(item["start_time"]),
        end_time=_iso_to_dt(item["end_time"]),
        ttl=item.get("ttl"),
        status=item.get("status", "active"),  # type: ignore[arg-type]
    )
