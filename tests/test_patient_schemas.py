from datetime import UTC, date, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.patient import PatientCreate, PatientResponse, PatientUpdate, calculate_age

VALID = {
    "first_name": "  Aarav ",
    "last_name": "Ramesh",
    "date_of_birth": "2002-05-14",
    "gender": "male",
    "phone": "+91 98765-43210",
    "address": "12 MG Road, Bengaluru",
}


def test_create_accepts_valid_data_and_normalizes():
    patient = PatientCreate(**VALID)

    assert patient.first_name == "Aarav"
    assert patient.phone == "+919876543210"
    assert patient.date_of_birth == date(2002, 5, 14)


@pytest.mark.parametrize("last_name", [None, "", "   "])
def test_create_allows_missing_last_name(last_name):
    patient = PatientCreate(**{**VALID, "last_name": last_name})

    assert patient.last_name is None


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("first_name", ""),
        ("first_name", "x" * 51),
        ("gender", "unknown"),
        ("phone", "12345"),
        ("phone", "98765abcde"),
        ("address", "abc"),
        ("date_of_birth", "not-a-date"),
        ("date_of_birth", (datetime.now(UTC).date() + timedelta(days=1)).isoformat()),
        ("date_of_birth", "1890-01-01"),
    ],
)
def test_create_rejects_invalid_field(field, value):
    with pytest.raises(ValidationError) as exc:
        PatientCreate(**{**VALID, field: value})

    assert exc.value.errors()[0]["loc"] == (field,)


def test_create_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        PatientCreate(**VALID, patient_id="PAT-9999")


def test_update_accepts_partial_data():
    update = PatientUpdate(phone="9876543210")

    assert update.model_dump(exclude_unset=True) == {"phone": "9876543210"}


def test_update_allows_clearing_last_name():
    assert PatientUpdate(last_name=None).model_dump(exclude_unset=True) == {"last_name": None}


@pytest.mark.parametrize("payload", [{}, {"first_name": None}, {"patient_id": "PAT-0002"}])
def test_update_rejects_empty_null_or_id_change(payload):
    with pytest.raises(ValidationError):
        PatientUpdate(**payload)


def test_response_computes_full_name_and_age_and_hides_mongo_id():
    now = datetime.now(UTC)
    doc = {
        "_id": "ignored",
        "patient_id": "PAT-0001",
        **VALID,
        "first_name": "Aarav",
        "created_at": now,
        "updated_at": now,
    }

    body = PatientResponse.model_validate(doc).model_dump()

    assert "_id" not in body
    assert body["full_name"] == "Aarav Ramesh"
    assert body["age"] == calculate_age(date(2002, 5, 14))


def test_full_name_without_last_name():
    now = datetime.now(UTC)
    doc = {**VALID, "patient_id": "PAT-0002", "first_name": "Aarav", "last_name": None}
    doc |= {"created_at": now, "updated_at": now}

    assert PatientResponse.model_validate(doc).full_name == "Aarav"


@pytest.mark.parametrize(
    ("today", "expected"),
    [(date(2026, 5, 13), 23), (date(2026, 5, 14), 24), (date(2026, 12, 31), 24)],
)
def test_calculate_age_handles_birthday_boundary(today, expected):
    assert calculate_age(date(2002, 5, 14), today) == expected
