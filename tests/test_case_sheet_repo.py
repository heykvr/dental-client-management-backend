from datetime import date

import pytest

from app.repositories.case_sheet_repo import CaseSheetRepository
from app.repositories.patient_repo import PatientRepository

PATIENT = {
    "first_name": "Aarav",
    "last_name": "Ramesh",
    "date_of_birth": date(2002, 5, 14),
    "gender": "male",
    "phone": "+919876543210",
    "address": "12 MG Road, Bengaluru",
}


@pytest.fixture
async def repo(db):
    await PatientRepository(db).create("PAT-0001", PATIENT)
    repo = CaseSheetRepository(db)
    await repo.ensure_indexes()
    return repo


async def test_patient_is_created_with_embedded_empty_case_sheet(repo, db):
    # One document holds both: created in a single atomic insert
    assert await db["patients"].count_documents({}) == 1
    assert "case_sheets" not in await db.list_collection_names()

    doc = await repo.get_patient_with_case_sheet("PAT-0001")

    sheet = doc["case_sheet"]
    assert doc["first_name"] == "Aarav"
    assert sheet["status"] == "not_started"
    assert sheet["chief_complaint"] == {"complaint": None, "duration": None}
    assert sheet["ai_summary"]["text"] is None
    assert "_id" not in doc


async def test_save_updates_only_case_sheet_fields(repo):
    complaint = {"complaint": "Tooth pain", "duration": "3 days"}

    doc = await repo.save("PAT-0001", {"chief_complaint": complaint}, "pending")

    assert doc["case_sheet"]["chief_complaint"] == complaint
    assert doc["case_sheet"]["investigation"]["tooth_area"] is None
    assert doc["case_sheet"]["status"] == "pending"
    assert doc["case_sheet"]["updated_at"] >= doc["case_sheet"]["created_at"]
    # Patient details untouched
    assert doc["first_name"] == "Aarav"
    assert doc["updated_at"] == doc["created_at"]


async def test_save_unknown_patient_returns_none_and_creates_nothing(repo, db):
    assert (
        await repo.save("PAT-9999", {"diagnosis": {"diagnosis": "x", "notes": None}}, "pending")
        is None
    )
    assert await db["patients"].count_documents({}) == 1


async def test_create_empty_never_overwrites_existing_sheet(repo):
    await repo.save("PAT-0001", {"diagnosis": {"diagnosis": "Caries", "notes": None}}, "pending")

    await repo.create_empty("PAT-0001")

    doc = await repo.get_patient_with_case_sheet("PAT-0001")
    assert doc["case_sheet"]["diagnosis"]["diagnosis"] == "Caries"


async def test_create_empty_restores_missing_sheet_but_never_creates_a_patient(repo, db):
    await db["patients"].update_one({"patient_id": "PAT-0001"}, {"$unset": {"case_sheet": ""}})

    await repo.create_empty("PAT-0001")
    await repo.create_empty("PAT-9999")

    doc = await repo.get_patient_with_case_sheet("PAT-0001")
    assert doc["case_sheet"]["status"] == "not_started"
    assert await db["patients"].count_documents({}) == 1


async def test_count_by_status(repo):
    await PatientRepository(repo._collection.database).create("PAT-0002", PATIENT)
    await repo.save(
        "PAT-0002", {"chief_complaint": {"complaint": "x", "duration": None}}, "pending"
    )

    assert await repo.count_by_status() == {"not_started": 1, "pending": 1}
