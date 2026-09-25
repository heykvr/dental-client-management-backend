from datetime import timedelta

import pytest
from pymongo import MongoClient

from app.core.exceptions import AIUnavailableError
from app.core.time import utc_now
from tests.conftest import TEST_DB_NAME, TEST_MONGODB_URI

PATIENT = {
    "first_name": "Aarav",
    "last_name": "Ramesh",
    "date_of_birth": "2002-05-14",
    "gender": "male",
    "phone": "+919876543210",
    "address": "12 MG Road, Bengaluru",
}
SHEET_URL = "/api/v1/patients/PAT-0001/case-sheet"
SUMMARY_URL = "/api/v1/patients/PAT-0001/summary"
PATIENT_URL = "/api/v1/patients/PAT-0001"
COMPLAINT = {"chief_complaint": {"complaint": "Tooth pain", "duration": "3 days"}}

# Each test uses its own client IP, so the AI limit (3/minute) is predictable per test
IP = {"X-Forwarded-For": "203.0.113.10"}


@pytest.fixture
def patient(client):
    assert client.post("/api/v1/patients", json=PATIENT, headers=IP).status_code == 201


def summary(client):
    return client.get(SHEET_URL, headers=IP).json()["ai_summary"]


# ------------------------------------------------------------------ automatic regeneration


def test_saving_case_sheet_generates_summary_in_background(client, patient, fake_ai):
    response = client.put(SHEET_URL, json=COMPLAINT, headers=IP)

    assert response.status_code == 200
    assert response.json()["ai_summary"]["state"] == "generating"  # save returned instantly
    after = summary(client)  # background task has run by now
    assert (after["state"], after["text"], after["is_stale"]) == ("ready", fake_ai.text, False)
    assert len(fake_ai.calls) == 1


def test_saving_same_content_again_does_not_call_ai(client, patient, fake_ai):
    client.put(SHEET_URL, json=COMPLAINT, headers=IP)
    client.put(SHEET_URL, json=COMPLAINT, headers=IP)

    assert len(fake_ai.calls) == 1


def test_empty_sheet_never_calls_ai(client, patient, fake_ai):
    client.put(SHEET_URL, json={"diagnosis": {"diagnosis": "", "notes": ""}}, headers=IP)

    assert fake_ai.calls == []
    assert summary(client)["state"] is None


def test_phone_edit_does_not_regenerate_but_name_edit_does(client, patient, fake_ai):
    client.put(SHEET_URL, json=COMPLAINT, headers=IP)

    client.put(PATIENT_URL, json={"phone": "+911111111111"}, headers=IP)
    assert len(fake_ai.calls) == 1

    client.put(PATIENT_URL, json={"first_name": "Arav"}, headers=IP)
    assert len(fake_ai.calls) == 2
    assert "Name: Arav Ramesh" in fake_ai.calls[-1]["contents"]


def test_ai_failure_in_background_shows_failed_but_save_succeeds(client, patient, fake_ai):
    fake_ai.error = AIUnavailableError()

    response = client.put(SHEET_URL, json=COMPLAINT, headers=IP)

    assert response.status_code == 200
    assert response.json()["chief_complaint"]["complaint"] == "Tooth pain"
    assert summary(client)["state"] == "failed"


def test_auto_runs_count_against_ai_limit_and_saves_still_work(client, patient, fake_ai):
    for n in range(4):  # 4 different contents; AI limit is 3/minute
        response = client.put(
            SHEET_URL, json={"chief_complaint": {"complaint": f"Pain {n}"}}, headers=IP
        )
        assert response.status_code == 200

    assert len(fake_ai.calls) == 3
    assert summary(client)["is_stale"] is True  # 4th save: summary shows as outdated


def test_stuck_generation_is_reported_as_failed(client, patient):
    client.put(SHEET_URL, json=COMPLAINT, headers=IP)
    with MongoClient(TEST_MONGODB_URI, tz_aware=True) as mongo:
        mongo[TEST_DB_NAME]["patients"].update_one(
            {"patient_id": "PAT-0001"},
            {
                "$set": {
                    "case_sheet.ai_summary.state": "generating",
                    "case_sheet.ai_summary.requested_at": utc_now() - timedelta(minutes=3),
                }
            },
        )

    assert summary(client)["state"] == "failed"


# --------------------------------------------------------------- manual Regenerate / Retry


def test_manual_regenerate_returns_updated_case_sheet(client, patient, fake_ai):
    client.put(SHEET_URL, json=COMPLAINT, headers=IP)
    fake_ai.text = "Regenerated summary."

    response = client.post(SUMMARY_URL, headers=IP)

    assert response.status_code == 200
    assert response.json()["ai_summary"]["text"] == "Regenerated summary."
    assert response.json()["patient_id"] == "PAT-0001"


def test_manual_on_not_started_sheet_is_409(client, patient, fake_ai):
    response = client.post(SUMMARY_URL, headers=IP)

    assert response.status_code == 409
    assert response.json()["code"] == "CASE_SHEET_REQUIRED"
    assert fake_ai.calls == []


def test_manual_when_ai_is_down_is_503(client, patient, fake_ai):
    fake_ai.error = AIUnavailableError()
    client.put(SHEET_URL, json=COMPLAINT, headers=IP)

    response = client.post(SUMMARY_URL, headers=IP)

    assert response.status_code == 503
    assert response.json()["code"] == "AI_UNAVAILABLE"
    assert summary(client)["state"] == "failed"


def test_manual_unknown_patient_is_404(client):
    response = client.post("/api/v1/patients/PAT-9999/summary", headers=IP)

    assert response.status_code == 404


def test_manual_is_ai_rate_limited(client, patient):
    client.put(SHEET_URL, json=COMPLAINT, headers=IP)  # uses 1 of 3 AI calls (auto)

    codes = [client.post(SUMMARY_URL, headers=IP).status_code for _ in range(3)]

    assert codes == [200, 200, 429]
