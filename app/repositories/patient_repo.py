import asyncio
import re
from datetime import date, datetime
from typing import Any

from pymongo import ASCENDING, DESCENDING, IndexModel, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.core.time import utc_now
from app.repositories.case_sheet_repo import empty_case_sheet

# Never return Mongo's internal _id. Patient reads leave out the clinical parts of the
# embedded case sheet (it has its own endpoint) and keep only its status + last update,
# so the list can show "Not started / Pending / Completed" without loading clinical data.
PATIENT_ONLY = {
    "_id": 0,
    "case_sheet.chief_complaint": 0,
    "case_sheet.investigation": 0,
    "case_sheet.diagnosis": 0,
    "case_sheet.ai_summary": 0,
    "case_sheet.created_at": 0,
}


# How the list can be sorted (the API's `sort` values) and the fields behind each
SORT_FIELDS: dict[str, dict[str, int]] = {
    "created_at": {"created_at": 1},
    "name": {"first_name": 1, "last_name": 1},
    "patient_id": {},  # patient_id is always added as the final key
    "status": {"_status_rank": 1},
}
STATUS_ORDER = ["not_started", "pending", "completed"]
CASE_INSENSITIVE = {"locale": "en", "strength": 2}


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
        # One insert = patient + its empty case sheet, atomically (1:1, embedded)
        now = utc_now()
        doc = {"patient_id": patient_id, **_to_db(fields), "created_at": now, "updated_at": now}
        await self._collection.insert_one({**doc, "case_sheet": empty_case_sheet(now)})
        return {**doc, "case_sheet": {"status": "not_started", "updated_at": now}}

    async def get(self, patient_id: str) -> dict[str, Any] | None:
        return await self._collection.find_one({"patient_id": patient_id}, PATIENT_ONLY)

    async def list(
        self,
        search: str | None,
        skip: int,
        limit: int,
        sort: str = "created_at",
        order: str = "desc",
    ) -> tuple[list[dict[str, Any]], int]:
        query = _search_filter(search)
        direction = ASCENDING if order == "asc" else DESCENDING
        pipeline: list[dict[str, Any]] = [{"$match": query}]
        if sort == "status":
            # Logical order (needs attention first when ascending), not alphabetical
            pipeline.append(
                {
                    "$addFields": {
                        "_status_rank": {"$indexOfArray": [STATUS_ORDER, "$case_sheet.status"]}
                    }
                }
            )
        # patient_id as the last key keeps the order stable when values are equal
        sort_keys = {**SORT_FIELDS[sort], "patient_id": direction}
        pipeline += [
            {"$sort": {field: direction for field in sort_keys}},
            {"$skip": skip},
            {"$limit": limit},
            {"$project": {**PATIENT_ONLY, "_status_rank": 0} if sort == "status" else PATIENT_ONLY},
        ]
        # Case-insensitive comparison, so "aarav" and "Aarav" sort together
        cursor = await self._collection.aggregate(pipeline, collation=CASE_INSENSITIVE)
        # The page and the total are fetched at the same time
        items, total = await asyncio.gather(
            cursor.to_list(), self._collection.count_documents(query)
        )
        return items, total

    async def update(self, patient_id: str, changes: dict[str, Any]) -> dict[str, Any] | None:
        return await self._collection.find_one_and_update(
            {"patient_id": patient_id},
            {"$set": {**_to_db(changes), "updated_at": utc_now()}},
            projection=PATIENT_ONLY,
            return_document=ReturnDocument.AFTER,
        )

    async def count(self, created_since: datetime | None = None) -> int:
        query = {"created_at": {"$gte": created_since}} if created_since else {}
        return await self._collection.count_documents(query)

    async def registrations_by_period(
        self, start: datetime, end: datetime, date_format: str, timezone: str
    ) -> dict[str, int]:
        """Count patients created in [start, end), grouped by period label in the given timezone,
        e.g. {"2026-09": 7} for date_format "%Y-%m"."""
        pipeline = [
            {"$match": {"created_at": {"$gte": start, "$lt": end}}},
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": date_format,
                            "date": "$created_at",
                            "timezone": timezone,
                        }
                    },
                    "count": {"$sum": 1},
                }
            },
        ]
        cursor = await self._collection.aggregate(pipeline)
        return {row["_id"]: row["count"] async for row in cursor}
