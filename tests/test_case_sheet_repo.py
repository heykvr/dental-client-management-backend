import pytest
from pymongo.errors import DuplicateKeyError

from app.repositories.case_sheet_repo import CaseSheetRepository


@pytest.fixture
async def repo(db):
    repo = CaseSheetRepository(db)
    await repo.ensure_indexes()
    return repo


async def test_create_empty_sheet(repo):
    await repo.create_empty("PAT-0001")

    sheet = await repo.get("PAT-0001")

    assert sheet["status"] == "not_started"
    assert sheet["chief_complaint"] == {"complaint": None, "duration": None}
    assert sheet["diagnosis"] == {"diagnosis": None, "notes": None}
    assert sheet["ai_summary"]["text"] is None
    assert "_id" not in sheet


async def test_create_empty_twice_keeps_existing_data(repo):
    await repo.create_empty("PAT-0001")
    await repo.save("PAT-0001", {"diagnosis": {"diagnosis": "Caries", "notes": None}}, "pending")

    await repo.create_empty("PAT-0001")

    sheet = await repo.get("PAT-0001")
    assert sheet["diagnosis"]["diagnosis"] == "Caries"
    assert sheet["status"] == "pending"


async def test_save_replaces_only_given_sections(repo):
    await repo.create_empty("PAT-0001")
    complaint = {"complaint": "Tooth pain", "duration": "3 days"}

    saved = await repo.save("PAT-0001", {"chief_complaint": complaint}, "pending")

    assert saved["chief_complaint"] == complaint
    assert saved["investigation"]["tooth_area"] is None
    assert saved["status"] == "pending"
    assert saved["updated_at"] >= saved["created_at"]
    assert "_id" not in saved


async def test_save_creates_missing_sheet(repo):
    saved = await repo.save(
        "PAT-0002", {"diagnosis": {"diagnosis": "Caries", "notes": None}}, "pending"
    )

    assert saved["patient_id"] == "PAT-0002"
    assert saved["ai_summary"]["text"] is None


async def test_get_missing_sheet_returns_none(repo):
    assert await repo.get("PAT-9999") is None


async def test_one_sheet_per_patient_is_enforced(repo, db):
    await repo.create_empty("PAT-0001")

    with pytest.raises(DuplicateKeyError):
        await db["case_sheets"].insert_one({"patient_id": "PAT-0001"})
