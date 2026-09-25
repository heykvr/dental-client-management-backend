from datetime import UTC, datetime

import pytest

from app.core.exceptions import InvalidRequestError
from app.repositories.case_sheet_repo import CaseSheetRepository
from app.repositories.patient_repo import PatientRepository
from app.services.dashboard_service import DashboardService

# "Now" = 2026-09-25 12:00 IST
NOW = datetime(2026, 9, 25, 6, 30, tzinfo=UTC)


def utc(*args) -> datetime:
    return datetime(*args, tzinfo=UTC)


async def add_patient(db, n: int, created_at: datetime, status: str = "not_started"):
    patient_id = f"PAT-{n:04d}"
    await db["patients"].insert_one(
        {
            "patient_id": patient_id,
            "first_name": f"Patient{n}",
            "last_name": None,
            "date_of_birth": "2000-01-01",
            "gender": "other",
            "phone": "+919999999999",
            "address": "Somewhere in India",
            "created_at": created_at,
            "updated_at": created_at,
            "case_sheet": {"status": status},
        }
    )


@pytest.fixture
def service(db):
    return DashboardService(PatientRepository(db), CaseSheetRepository(db), clock=lambda: NOW)


async def test_stats_counts(service, db):
    await add_patient(db, 1, utc(2026, 7, 10), "completed")
    await add_patient(db, 2, utc(2026, 9, 2), "pending")
    await add_patient(db, 3, utc(2026, 9, 20), "not_started")

    stats = await service.get_stats()

    assert stats.total_patients == 3
    assert stats.new_patients_this_month == 2
    assert stats.completed_case_sheets == 1
    assert stats.pending_case_sheets == 2  # pending + not_started
    assert [p.patient_id for p in stats.recent_patients] == ["PAT-0003", "PAT-0002", "PAT-0001"]


async def test_month_boundary_uses_ist(service, db):
    # 2026-08-31 19:00 UTC = 2026-09-01 00:30 IST -> September, i.e. "this month"
    await add_patient(db, 1, utc(2026, 8, 31, 19, 0))
    # 2026-08-31 18:00 UTC = 2026-08-31 23:30 IST -> August
    await add_patient(db, 2, utc(2026, 8, 31, 18, 0))

    stats = await service.get_stats()
    trend = {p.period: p.count for p in stats.registration_trend.points}

    assert stats.new_patients_this_month == 1
    assert (trend["2026-08"], trend["2026-09"]) == (1, 1)


async def test_default_trend_is_last_six_months_zero_filled(service, db):
    await add_patient(db, 1, utc(2026, 5, 15))
    await add_patient(db, 2, utc(2026, 9, 1))
    await add_patient(db, 3, utc(2026, 9, 2))
    await add_patient(db, 4, utc(2026, 3, 1))  # older than 6 months: not included

    trend = await service.get_trend()

    assert trend.granularity == "month"
    assert [(p.period, p.count) for p in trend.points] == [
        ("2026-04", 0),
        ("2026-05", 1),
        ("2026-06", 0),
        ("2026-07", 0),
        ("2026-08", 0),
        ("2026-09", 2),
    ]


async def test_default_trend_crosses_year_boundary(db):
    service = DashboardService(
        PatientRepository(db), CaseSheetRepository(db), clock=lambda: utc(2027, 2, 10)
    )

    trend = await service.get_trend()

    assert [p.period for p in trend.points] == [
        "2026-09",
        "2026-10",
        "2026-11",
        "2026-12",
        "2027-01",
        "2027-02",
    ]


async def test_year_filter_gives_twelve_months(service, db):
    await add_patient(db, 1, utc(2025, 12, 31, 12, 0))  # still 2025 in IST
    await add_patient(db, 2, utc(2025, 12, 31, 19, 0))  # 2026-01-01 00:30 IST
    await add_patient(db, 3, utc(2026, 6, 15))

    trend = await service.get_trend(year=2026)
    counts = {p.period: p.count for p in trend.points}

    assert trend.granularity == "month"
    assert len(trend.points) == 12
    assert (counts["2026-01"], counts["2026-06"], sum(counts.values())) == (1, 1, 2)


async def test_year_and_month_filter_gives_days(service, db):
    await add_patient(db, 1, utc(2026, 9, 4, 20, 0))  # 2026-09-05 01:30 IST
    await add_patient(db, 2, utc(2026, 9, 5, 10, 0))

    trend = await service.get_trend(year=2026, month=9)
    counts = {p.period: p.count for p in trend.points}

    assert trend.granularity == "day"
    assert len(trend.points) == 30
    assert counts["2026-09-05"] == 2
    assert counts["2026-09-04"] == 0


@pytest.mark.parametrize(("year", "days"), [(2028, 29), (2026, 28)])
async def test_february_day_count_handles_leap_years(service, year, days):
    trend = await service.get_trend(year=year, month=2)

    assert len(trend.points) == days


async def test_month_without_year_is_rejected(service):
    with pytest.raises(InvalidRequestError):
        await service.get_trend(month=9)


def test_http_endpoints(client):
    stats = client.get("/api/v1/dashboard/stats")
    trend = client.get("/api/v1/dashboard/trend", params={"year": 2026, "month": 2})
    bad = client.get("/api/v1/dashboard/trend", params={"month": 9})
    out_of_range = client.get("/api/v1/dashboard/trend", params={"year": 2026, "month": 13})

    assert stats.status_code == 200
    assert stats.json()["total_patients"] == 0
    assert len(stats.json()["registration_trend"]["points"]) == 6
    assert trend.json()["granularity"] == "day"
    assert bad.status_code == 422
    assert bad.json()["code"] == "VALIDATION_ERROR"
    assert out_of_range.status_code == 422
