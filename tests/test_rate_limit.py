import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.core.exceptions import register_exception_handlers
from app.core.rate_limit import get_client_ip, rate_limit

URL = "/api/v1/patients"


def ip(address: str) -> dict[str, str]:
    return {"X-Forwarded-For": address}


def test_default_limit_blocks_the_11th_request(client):
    codes = [client.get(URL, headers=ip("1.1.1.1")).status_code for _ in range(10)]
    blocked = client.get(URL, headers=ip("1.1.1.1"))

    assert codes == [200] * 10
    assert blocked.status_code == 429
    assert blocked.json()["code"] == "RATE_LIMITED"
    assert 1 <= int(blocked.headers["Retry-After"]) <= 60


def test_limit_covers_every_api_endpoint(client):
    # Mixed endpoints share the same default bucket
    for _ in range(5):
        client.get("/api/v1/dashboard/stats", headers=ip("2.2.2.2"))
        client.get(URL, headers=ip("2.2.2.2"))

    assert client.get("/api/v1/dashboard/trend", headers=ip("2.2.2.2")).status_code == 429


def test_health_is_never_limited(client):
    assert {client.get("/health", headers=ip("3.3.3.3")).status_code for _ in range(25)} == {200}


def test_spoofed_forwarded_for_cannot_dodge_the_limit(client):
    # An attacker changes the leftmost (fake) entry every time; Render's entry stays the same
    for n in range(10):
        client.get(URL, headers=ip(f"10.0.0.{n}, 4.4.4.4"))

    assert client.get(URL, headers=ip("10.9.9.9, 4.4.4.4")).status_code == 429


def test_different_clients_have_separate_limits(client):
    for _ in range(10):
        client.get(URL, headers=ip("5.5.5.5"))

    assert client.get(URL, headers=ip("5.5.5.5")).status_code == 429
    assert client.get(URL, headers=ip("6.6.6.6")).status_code == 200


def test_rate_limited_response_is_readable_cross_origin(client):
    origin = "http://localhost:5173"
    for _ in range(10):
        client.get(URL, headers={**ip("7.7.7.7"), "Origin": origin})

    blocked = client.get(URL, headers={**ip("7.7.7.7"), "Origin": origin})

    assert blocked.status_code == 429
    assert blocked.headers["access-control-allow-origin"] == origin
    assert "retry-after" in blocked.headers["access-control-expose-headers"].lower()


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        ({"x-forwarded-for": "9.9.9.9"}, "9.9.9.9"),
        ({"x-forwarded-for": "6.6.6.6, 1.2.3.4"}, "1.2.3.4"),
        ({"x-forwarded-for": " 6.6.6.6 ,  1.2.3.4 "}, "1.2.3.4"),
        ({}, "127.0.0.1"),
    ],
)
def test_get_client_ip_uses_rightmost_entry(headers, expected):
    scope = {
        "type": "http",
        "headers": [(k.encode(), v.encode()) for k, v in headers.items()],
        "client": ("127.0.0.1", 1234),
    }

    assert get_client_ip(Request(scope)) == expected


def test_sliding_window_blocks_burst_across_minute_boundary(monkeypatch):
    """With a fixed window, 3 requests at 0:59 and 3 more at 1:01 would all pass.
    A sliding window counts the last 60 seconds, so the second burst is blocked."""
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/limited", dependencies=[rate_limit("3/minute", "sliding-test")])
    async def limited():
        return {"ok": True}

    client = TestClient(app)
    now = [1_000_059.0]  # 59 s into a minute
    monkeypatch.setattr(time, "time", lambda: now[0])

    assert [client.get("/limited").status_code for _ in range(3)] == [200, 200, 200]

    now[0] += 2  # 1:01, a new "fixed" minute, but only 2 s later
    assert client.get("/limited").status_code == 429

    now[0] += 59  # just over 60 s after the first burst: they have slid out of the window
    assert client.get("/limited").status_code == 200
