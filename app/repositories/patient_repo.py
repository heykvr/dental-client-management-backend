import re
from datetime import UTC, date, datetime
from typing import Any

from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

# Never return Mongo's internal _id to callers
NO_ID = {"_id": 0}


def _now() -> datetime:
    # MongoDB stores milliseconds; truncate so returned values match what is saved
    now = datetime.now(UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


def _to_db(fields: dict[str, Any]) -> dict[str, Any]:
    # date_of_birth is a calendar date: stored as "YYYY-MM-DD" text, never as a datetime
    return {k: v.isoformat() if isinstance(v, date) else v for k, v in fields.items()}


def _search_filter(search: str | None) -> dict[str, Any]:
    """Each word must match first name, last name or phone (case-insensitive, regex-escaped)."""
    words = (search or "").split()
    if not words:
        return {}
    clauses = []
    for word in words:
        pattern = {"$regex": re.escape(word), "$options": "i"}
        clauses.append(
            {"$or": [{"first_name": pattern}, {"last_name": pattern}, {"phone": pattern}]}
        )
    return {"$and": clauses}


class PatientRepository:
    def __init__(self, db: AsyncDatabase):
        self._collection = db["patients"]

    async def ensure_indexes(self) -> None:
        await self._collection.create_indexes(
            [
                IndexModel([("patient_id", ASCENDING)], unique=True),
                IndexModel([("created_at", DESCENDING)]),
                IndexModel([("first_name", ASCENDING)]),
                IndexModel([("last_name", ASCENDING)]),
                IndexModel([("phone", ASCENDING)]),
            ]
        )

    async def create(self, patient_id: str, fields: dict[str, Any]) -> dict[str, Any]:
        now = _now()
        doc = {"patient_id": patient_id, **_to_db(fields), "created_at": now, "updated_at": now}
        await self._collection.insert_one(doc)
        doc.pop("_id", None)
        return doc

    async def get(self, patient_id: str) -> dict[str, Any] | None:
        return await self._collection.find_one({"patient_id": patient_id}, NO_ID)

    async def list(
        self, search: str | None, skip: int, limit: int
    ) -> tuple[list[dict[str, Any]], int]:
        query = _search_filter(search)
        cursor = (
            self._collection.find(query, NO_ID)
            .sort([("created_at", DESCENDING), ("patient_id", DESCENDING)])
            .skip(skip)
            .limit(limit)
        )
        items = await cursor.to_list()
        total = await self._collection.count_documents(query)
        return items, total

    async def update(self, patient_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        return await self._collection.find_one_and_update(
            {"patient_id": patient_id},
            {"$set": {**_to_db(changes), "updated_at": _now()}},
            projection=NO_ID,
            return_document=ReturnDocument.AFTER,
        )
