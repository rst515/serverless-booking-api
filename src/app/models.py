from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class BookingCreate(BaseModel):
    user_id: str = Field(..., min_length=1)
    resource_id: str = Field(..., min_length=1)
    start_time: datetime
    end_time: datetime
    # seconds before start_time to send reminder; we convert to TTL at creation
    reminder_lead_seconds: int | None = Field(default=900, ge=60)


class BookingUpdate(BaseModel):
    resource_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    reminder_lead_seconds: int | None = Field(default=None, ge=60)


class Booking(BaseModel):
    booking_id: str
    user_id: str
    resource_id: str
    start_time: datetime
    end_time: datetime
    ttl: int | None = None  # epoch seconds when reminder should trigger
    status: Literal["active", "cancelled"] = "active"
