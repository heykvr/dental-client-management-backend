from fastapi.testclient import TestClient

import app.main
from app.main import app as fastapi_app


def test_health_ok_when_database_reachable():
    with TestClient(fastapi_app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


def test_health_503_when_database_unreachable(monkeypatch):
    async def failing_ping(db):
        return False

    monkeypatch.setattr(app.main, "ping", failing_ping)

    with TestClient(fastapi_app) as client:
        response = client.get("/health")

    assert response.status_code == 503
    assert response.json() == {"status": "error", "database": "unavailable"}
