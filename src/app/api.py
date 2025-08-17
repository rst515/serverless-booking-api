from __future__ import annotations

from aws_lambda_powertools import Logger, Tracer
from aws_lambda_powertools.metrics import Metrics, MetricUnit
from fastapi import FastAPI, HTTPException
from starlette.responses import Response

from app import dal
from app.models import Booking, BookingCreate, BookingUpdate

logger = Logger()
tracer = Tracer()
metrics = Metrics(namespace="BookingAPI")

app = FastAPI(title="Serverless Booking API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@tracer.capture_method
@app.post("/bookings", response_model=Booking, status_code=201)
def create_booking(payload: BookingCreate) -> Booking:
    metrics.add_metric(name="CreateBooking", value=1, unit=MetricUnit.Count)
    return dal.create_booking(payload)


@tracer.capture_method
@app.get("/bookings/{booking_id}", response_model=Booking)
def get_booking(booking_id: str) -> Booking:
    try:
        return dal.get_booking(booking_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Booking not found") from exc


@tracer.capture_method
@app.get("/users/{user_id}/bookings", response_model=list[Booking])
def list_bookings(user_id: str) -> list[Booking]:
    return dal.list_bookings_for_user(user_id)


@tracer.capture_method
@app.put("/bookings/{booking_id}", response_model=Booking)
def update_booking(booking_id: str, payload: BookingUpdate) -> Booking:
    try:
        return dal.update_booking(booking_id, payload)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Booking not found") from exc


@tracer.capture_method
@app.delete("/bookings/{booking_id}")
def delete_booking(booking_id: str) -> Response:
    dal.delete_booking(booking_id)
    return Response(status_code=204)



@tracer.capture_method
@app.post("/bookings/{booking_id}/cancel", response_model=Booking)
def cancel_booking(booking_id: str) -> Booking:
    return dal.cancel_booking(booking_id)
