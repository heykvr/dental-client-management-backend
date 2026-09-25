from pymongo import ReturnDocument
from pymongo.asynchronous.database import AsyncDatabase

PATIENT_COUNTER_ID = "patient_id"


class CounterRepository:
    """Atomic sequence numbers. One document per sequence: {_id: name, seq: int}."""

    def __init__(self, db: AsyncDatabase):
        self._collection = db["counters"]

    async def ensure_patient_counter(self) -> None:
        # Called at startup: creates the counter once, never resets an existing one
        await self._collection.update_one(
            {"_id": PATIENT_COUNTER_ID}, {"$setOnInsert": {"seq": 0}}, upsert=True
        )

    async def next_patient_id(self) -> str:
        # $inc is atomic, so concurrent requests always get different numbers
        doc = await self._collection.find_one_and_update(
            {"_id": PATIENT_COUNTER_ID},
            {"$inc": {"seq": 1}},
            upsert=True,
            return_document=ReturnDocument.AFTER,
        )
        return f"PAT-{doc['seq']:04d}"
