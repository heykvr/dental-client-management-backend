from datetime import date

import pytest
from pymongo.errors import DuplicateKeyError

from app.repositories.patient_repo import PatientRepository


def fields(first_name="Aarav", last_name="Ramesh", phone="+919876543210"):
    return {
        "first_name": first_name,
        "last_name": last_name,
        "date_of_birth": date(2002, 5, 14),
        "gender": "male",
        "phone": phone,
        "address": "12 MG Road, Bengaluru",
    }


@pytest.fixture
async def repo(db):
    repo = PatientRepository(db)
    await repo.ensure_indexes()
    return repo


async def test_create_stores_dob_as_iso_string_and_hides_mongo_id(repo, db):
    created = await repo.create("PAT-0001", fields())

    raw = await db["patients"].find_one({"patient_id": "PAT-0001"})
    assert raw["date_of_birth"] == "2002-05-14"
    assert "_id" not in created
    assert created["created_at"] == created["updated_at"]


async def test_get_returns_patient_or_none(repo):
    await repo.create("PAT-0001", fields())

    found = await repo.get("PAT-0001")

    assert found["first_name"] == "Aarav"
    assert "_id" not in found
    assert await repo.get("PAT-9999") is None


async def test_list_is_newest_first_with_paging_and_total(repo):
    for n in range(1, 6):
        await repo.create(f"PAT-{n:04d}", fields(first_name=f"Patient{n}"))

    items, total = await repo.list(search=None, skip=0, limit=2)
    next_items, _ = await repo.list(search=None, skip=2, limit=2)

    assert total == 5
    assert [p["patient_id"] for p in items] == ["PAT-0005", "PAT-0004"]
    assert [p["patient_id"] for p in next_items] == ["PAT-0003", "PAT-0002"]


@pytest.mark.parametrize(
    ("search", "expected"),
    [
        ("aarav", ["PAT-0001"]),  # first name, case-insensitive
        ("SHARMA", ["PAT-0002"]),  # last name
        ("98765", ["PAT-0001"]),  # part of phone
        ("aarav ram", ["PAT-0001"]),  # each word matches first or last name
        ("aarav sharma", []),  # words match different patients: no result
        ("(", []),  # regex special characters are escaped, not an error
        ("  ", ["PAT-0002", "PAT-0001"]),  # blank search returns everyone
    ],
)
async def test_search(repo, search, expected):
    await repo.create("PAT-0001", fields())
    await repo.create("PAT-0002", fields("Priya", "Sharma", "+918888888888"))

    items, total = await repo.list(search=search, skip=0, limit=10)

    assert [p["patient_id"] for p in items] == expected
    assert total == len(expected)


async def test_update_changes_only_given_fields(repo):
    created = await repo.create("PAT-0001", fields())

    updated = await repo.update("PAT-0001", {"phone": "+911111111111", "last_name": None})

    assert updated["phone"] == "+911111111111"
    assert updated["last_name"] is None
    assert updated["first_name"] == "Aarav"
    assert updated["updated_at"] >= created["updated_at"]
    assert updated["created_at"] == created["created_at"]
    assert "_id" not in updated


async def test_returned_timestamps_match_stored_values(repo):
    created = await repo.create("PAT-0001", fields())

    assert (await repo.get("PAT-0001"))["created_at"] == created["created_at"]


async def test_update_missing_patient_returns_none(repo):
    assert await repo.update("PAT-9999", {"phone": "+911111111111"}) is None


async def test_duplicate_patient_id_is_rejected(repo):
    await repo.create("PAT-0001", fields())

    with pytest.raises(DuplicateKeyError):
        await repo.create("PAT-0001", fields())


async def test_patient_reads_include_only_case_sheet_status(repo, db):
    created = await repo.create("PAT-0001", fields())
    raw = await db["patients"].find_one({"patient_id": "PAT-0001"})
    items, _ = await repo.list(None, skip=0, limit=10)
    updated = await repo.update("PAT-0001", {"phone": "+911111111111"})

    assert raw["case_sheet"]["status"] == "not_started"
    for doc in (created, await repo.get("PAT-0001"), items[0], updated):
        # only the status + last update come back, never clinical data or the summary
        assert set(doc["case_sheet"]) == {"status", "updated_at"}
