"""Case sheets are EMBEDDED in the patient document (`patients.case_sheet`).

Why embedded: strictly one case sheet per patient, always read together with the patient,
and small/bounded. So one query loads the whole screen and creating a patient with its
empty case sheet is a single atomic write. See DECISIONS.md.
"""

from datetime import datetime
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


def empty_case_sheet(now: datetime) -> dict[str, Any]:
    """A new, empty case sheet (status not_started), embedded when a patient is created."""
    return {
        **CaseSheetContent().model_dump(),
        "status": "not_started",
        "ai_summary": EMPTY_SUMMARY,
        "created_at": now,
        "updated_at": now,
    }


class CaseSheetRepository:
    def __init__(self, db: AsyncDatabase):
        self._collection = db["patients"]

    async def ensure_indexes(self) -> None:
        # For dashboard status counts
        await self._collection.create_indexes([IndexModel([("case_sheet.status", ASCENDING)])])

    async def get_patient_with_case_sheet(self, patient_id: str) -> dict[str, Any] | None:
        """The whole patient document, including `case_sheet`, in one query."""
        return await self._collection.find_one({"patient_id": patient_id}, NO_ID)

    async def create_empty(self, patient_id: str) -> None:
        """Safety net for a patient without a case sheet. Never overwrites an existing one
        and never creates a patient."""
        await self._collection.update_one(
            {"patient_id": patient_id, "case_sheet": {"$exists": False}},
            {"$set": {"case_sheet": empty_case_sheet(utc_now())}},
        )

    async def save(
        self, patient_id: str, sections: dict[str, Any], status: str
    ) -> dict[str, Any] | None:
        """Replace the given sections and set the status. Only `case_sheet.*` sub-fields are
        written, so patient details are never touched. Returns the whole patient document."""
        updates = {f"case_sheet.{name}": value for name, value in sections.items()}
        return await self._collection.find_one_and_update(
            {"patient_id": patient_id},
            {
                "$set": {
                    **updates,
                    "case_sheet.status": status,
                    "case_sheet.updated_at": utc_now(),
                }
            },
            projection=NO_ID,
            return_document=ReturnDocument.AFTER,
        )

    async def set_summary_if_unchanged(
        self, patient_id: str, snapshot: dict[str, Any], summary: dict[str, Any]
    ) -> bool:
        """Save the AI summary only if the summarised data still equals `snapshot` (the values
        read before calling the AI). One atomic update: check and write together, so a newer
        edit always wins over an older, slower AI call. Returns False if data changed."""
        result = await self._collection.update_one(
            {"patient_id": patient_id, **snapshot},
            {"$set": {"case_sheet.ai_summary": summary}},
        )
        return result.matched_count == 1

    async def set_summary_state_if_unchanged(
        self, patient_id: str, snapshot: dict[str, Any], state: str
    ) -> bool:
        """Update only the summary state (e.g. "failed"), keeping the previous summary text."""
        result = await self._collection.update_one(
            {"patient_id": patient_id, **snapshot},
            {"$set": {"case_sheet.ai_summary.state": state}},
        )
        return result.matched_count == 1

    async def mark_generating(self, patient_id: str, requested_hash: str) -> None:
        """Summary is being (re)generated for the content with fingerprint `requested_hash`.
        The previous text stays visible until the new one is saved."""
        await self._collection.update_one(
            {"patient_id": patient_id},
            {
                "$set": {
                    "case_sheet.ai_summary.state": "generating",
                    "case_sheet.ai_summary.requested_hash": requested_hash,
                    "case_sheet.ai_summary.requested_at": utc_now(),
                }
            },
        )

    async def count_by_status(self) -> dict[str | None, int]:
        cursor = await self._collection.aggregate(
            [{"$group": {"_id": "$case_sheet.status", "count": {"$sum": 1}}}]
        )
        return {row["_id"]: row["count"] async for row in cursor}
