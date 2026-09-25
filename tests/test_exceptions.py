import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from app.core.exceptions import PatientNotFoundError, register_exception_handlers


class Payload(BaseModel):
    name: str = Field(min_length=2)
    age: int


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/missing")
    async def missing():
        raise PatientNotFoundError()

    @app.post("/validate")
    async def validate(payload: Payload):
        return payload

    @app.get("/crash")
    async def crash():
        raise RuntimeError("secret internal detail")

    return TestClient(app, raise_server_exceptions=False)


def test_app_error_uses_standard_shape(client):
    response = client.get("/missing")

    assert response.status_code == 404
    assert response.json() == {"detail": "Patient not found.", "code": "PATIENT_NOT_FOUND"}


def test_validation_error_lists_fields(client):
    response = client.post("/validate", json={"name": "A"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["detail"] == "Invalid request data."
    assert {e["field"] for e in body["errors"]} == {"name", "age"}


def test_unknown_route_uses_standard_shape(client):
    response = client.get("/does-not-exist")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not Found", "code": "NOT_FOUND"}


def test_unexpected_error_hides_internals(client):
    response = client.get("/crash")

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_ERROR"
    assert "secret" not in response.text
