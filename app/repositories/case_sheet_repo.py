from typing import Any

from pymongo import ASCENDING, IndexModel, ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

from app.core.time import utc_now
from app.schemas.case_sheet import CaseSheetContent

NO_ID = {"_id": 0}

EMPTY_SUMMARY = {
    "text": None,
    "generated_at": None,
    "model": None,
    "source_hash": None,
    "state": None,
}


class CaseSheetRepository:
    """One case sheet per patient, linked by patient_id (enforced by a unique index)."""

    def __init__(self, db: AsyncDatabase):
        self._collection = db["case_sheets"]

    async def ensure_indexes(self) -> None:
        await self._collection.create_indexes(
            [
                IndexModel([("patient_id", ASCENDING)], unique=True),
                IndexModel([("status", ASCENDING)]),
            ]
        )

    async def create_empty(self, patient_id: str) -> None:
        # $setOnInsert + upsert: creates the sheet once, never overwrites an existing one
        now = utc_now()
        await self._collection.update_one(
            {"patient_id": patient_id},
            {
                "$setOnInsert": {
                    **CaseSheetContent().model_dump(),
                    "status": "not_started",
                    "ai_summary": EMPTY_SUMMARY,
                    "created_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
        )

    async def get(self, patient_id: str) -> dict[str, Any] | None:
        return await self._collection.find_one({"patient_id": patient_id}, NO_ID)

    async def save(self, patient_id: str, sections: dict[str, Any], status: str) -> dict[str, Any]:
        """Replace the given sections and set the status. Creates the sheet if it is missing."""
        now = utc_now()
        return await self._collection.find_one_and_update(
            {"patient_id": patient_id},
            {
                "$set": {**sections, "status": status, "updated_at": now},
                "$setOnInsert": {"ai_summary": EMPTY_SUMMARY, "created_at": now},
            },
            upsert=True,
            projection=NO_ID,
            return_document=ReturnDocument.AFTER,
        )

    async def count_by_status(self) -> dict[str, int]:
        cursor = await self._collection.aggregate(
            [{"$group": {"_id": "$status", "count": {"$sum": 1}}}]
        )
        return {row["_id"]: row["count"] async for row in cursor}
