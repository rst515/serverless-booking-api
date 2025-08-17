from __future__ import annotations

from http import HTTPStatus
from typing import Any

from app.api_handler import lambda_handler


def _http_v2_event(path: str, method: str = "GET") -> dict[str, Any]:
    return {
        "version": "2.0",
        "rawPath": path,
        "routeKey": f"{method} {path}",
        "rawQueryString": "",
        "headers": {"host": "example.com"},
        "requestContext": {"http": {"method": method, "path": path, "protocol": "HTTP/1.1"}},
        "isBase64Encoded": False,
    }


def test_lambda_handler_health_ok() -> None:
    event = _http_v2_event("/health", "GET")
    resp = lambda_handler(event, context={})  # type: ignore[arg-type]
    assert isinstance(resp, dict)
    assert resp.get("statusCode") == HTTPStatus.OK
    assert "ok" in resp.get("body", "")
