from typing import Annotated

from fastapi import Depends, Request
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings


def create_client(settings: Settings) -> AsyncMongoClient:
    # Lazy: no network call until the first operation
    return AsyncMongoClient(settings.mongodb_uri, serverSelectionTimeoutMS=5000, tz_aware=True)


async def ping(db: AsyncDatabase) -> bool:
    try:
        await db.command("ping")
        return True
    except Exception:
        return False


def get_db(request: Request) -> AsyncDatabase:
    """FastAPI dependency: the database opened in the app lifespan."""
    return request.app.state.db


DbDep = Annotated[AsyncDatabase, Depends(get_db)]
