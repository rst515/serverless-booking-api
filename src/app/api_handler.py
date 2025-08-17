from __future__ import annotations

from typing import Any

from aws_lambda_powertools import Logger
from mangum import Mangum
from mangum.types import LambdaContext

from app.api import app

logger = Logger()
handler = Mangum(app)


def lambda_handler(event: dict[str, Any], context: LambdaContext) -> Any:
    # Normalize minimal API Gateway HTTP API v2.0 events for local/tests
    if isinstance(event, dict) and event.get("version") == "2.0":
        request_context = event.setdefault("requestContext", {})
        http_ctx = request_context.setdefault("http", {})
        http_ctx.setdefault("sourceIp", "127.0.0.1")
        http_ctx.setdefault("userAgent", "pytest")
        request_context.setdefault("stage", "$default")

    return handler(event, context)
