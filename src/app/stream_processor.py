from __future__ import annotations

import json
from typing import Any

import boto3
from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.utilities.typing import LambdaContext

logger = Logger()
tracer = Tracer()

_events = boto3.client("events")


@tracer.capture_lambda_handler
def lambda_handler(event: dict[str, Any], context: LambdaContext) -> None:
    # Triggered by DynamoDB stream when TTL expires -> record is removed
    for record in event.get("Records", []):
        if record.get("eventName") != "REMOVE":
            continue

        old_image = record.get("dynamodb", {}).get("OldImage", {})
        booking_id = old_image.get("booking_id", {}).get("S")
        user_id = old_image.get("user_id", {}).get("S")
        n = old_image.get("ttl", {}).get("N")

        # Parse TTL without exceptions; DynamoDB streams provide N as string
        ttl = int(n) if isinstance(n, str) and n.isdigit() else None

        if not booking_id or not user_id or ttl is None:
            # Not a TTL-driven removal of a booking with reminder set
            continue

        detail = {
            "version": "1.0",
            "type": "ReminderDue",
            "booking_id": booking_id,
            "user_id": user_id,
            "ttl": ttl,
        }
        logger.info("Emitting reminder event", extra=detail)

        _events.put_events(
            Entries=[
                {
                    "Source": "booking.reminder",
                    "DetailType": "ReminderDue",
                    "Detail": json.dumps(detail),
                }
            ]
        )
