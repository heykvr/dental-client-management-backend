from datetime import UTC, date, datetime
from functools import lru_cache
from typing import Annotated
from zoneinfo import ZoneInfo

from pydantic import PlainSerializer

from app.core.config import get_settings


def utc_now() -> datetime:
    """Current UTC time, truncated to milliseconds (MongoDB's precision),
    so values returned by the API match what is stored."""
    now = datetime.now(UTC)
    return now.replace(microsecond=now.microsecond // 1000 * 1000)


@lru_cache
def app_tz() -> ZoneInfo:
    """The clinic's timezone (IST by default). Used for calendar logic and API output."""
    return ZoneInfo(get_settings().app_timezone)


def local_today() -> date:
    """Today's date in the app timezone (not UTC)."""
    return datetime.now(app_tz()).date()


def _to_local_iso(value: datetime) -> str:
    return value.astimezone(app_tz()).isoformat(timespec="milliseconds")


# Datetime field that is stored in UTC but returned by the API in the app timezone,
# e.g. "2026-09-25T11:18:37.129+05:30"
LocalDatetime = Annotated[
    datetime, PlainSerializer(_to_local_iso, return_type=str, when_used="json")
]
