import pytest
from pymongo import MongoClient

from tests.conftest import TEST_DB_NAME, TEST_MONGODB_URI

PATIENT = {
    "first_name": "Aarav",
    "last_name": "Ramesh",
    "date_of_birth": "2002-05-14",
    "gender": "male",
    "phone": "+919876543210",
    "address": "12 MG Road, Bengaluru",
}
URL = "/api/v1/patients/PAT-0001/case-sheet"

CHIEF_COMPLAINT = {"complaint": "Pain in lower right back tooth", "duration": "3 days"}
INVESTIGATION = {
    "tooth_area": "46 - Lower Right First Molar",
    "clinical_findings": "Deep dental caries observed",
    "tenderness": True,
    "sensitivity": "Sensitive to hot and cold",
    "additional_findings": "No visible swelling",
}
DIAGNOSIS = {"diagnosis": "Deep dental caries with suspected pulpal involvement", "notes": None}


@pytest.fixture
def patient(client):
    assert client.post("/api/v1/patients", json=PATIENT).status_code == 201


def test_new_patient_has_empty_not_started_sheet(client, patient):
    response = client.get(URL)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "not_started"
    assert body["chief_complaint"] == {"complaint": None, "duration": None}
    assert body["ai_summary"] == {
        "text": None,
        "generated_at": None,
        "model": None,
        "state": None,
        "is_stale": False,
    }
    assert "_id" not in body


def test_status_flow_not_started_pending_completed(client, patient):
    step1 = client.put(URL, json={"chief_complaint": CHIEF_COMPLAINT}).json()
    assert step1["status"] == "pending"

    step2 = client.put(URL, json={"investigation": INVESTIGATION}).json()
    assert step2["status"] == "pending"
    assert step2["chief_complaint"] == CHIEF_COMPLAINT  # earlier section kept

    step3 = client.put(URL, json={"diagnosis": DIAGNOSIS}).json()
    assert step3["status"] == "completed"

    assert client.get(URL).json()["status"] == "completed"


def test_clearing_a_required_field_goes_back_to_pending(client, patient):
    client.put(
        URL,
        json={
            "chief_complaint": CHIEF_COMPLAINT,
            "investigation": INVESTIGATION,
            "diagnosis": DIAGNOSIS,
        },
    )

    body = client.put(URL, json={"diagnosis": {"diagnosis": "", "notes": "Review"}}).json()

    assert body["status"] == "pending"
    assert body["diagnosis"] == {"diagnosis": None, "notes": "Review"}


def test_unknown_patient_returns_404(client):
    for response in (client.get(URL), client.put(URL, json={"diagnosis": DIAGNOSIS})):
        assert response.status_code == 404
        assert response.json()["code"] == "PATIENT_NOT_FOUND"


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "completed"},
        {"investigation": {"tenderness": "maybe"}},
        {"chief_complaint": {"complaint": "x" * 1001}},
    ],
)
def test_invalid_payload_returns_422(client, patient, payload):
    response = client.put(URL, json=payload)

    assert response.status_code == 422
    assert response.json()["code"] == "VALIDATION_ERROR"


def test_summary_is_stale_when_content_changes_after_summary(client, patient):
    client.put(URL, json={"chief_complaint": CHIEF_COMPLAINT})
    with MongoClient(TEST_MONGODB_URI) as mongo:
        # Simulate a summary made from older content (Day 4 builds the real one)
        mongo[TEST_DB_NAME]["case_sheets"].update_one(
            {"patient_id": "PAT-0001"},
            {"$set": {"ai_summary.text": "Old summary", "ai_summary.source_hash": "old"}},
        )

    assert client.get(URL).json()["ai_summary"]["is_stale"] is True
