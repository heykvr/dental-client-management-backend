from typing import Annotated

from fastapi import APIRouter, Query

from app.api.deps import DashboardServiceDep
from app.schemas.dashboard import DashboardStats, RegistrationTrend

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/stats", summary="Dashboard cards, recent patients and the default 6-month trend")
async def get_stats(service: DashboardServiceDep) -> DashboardStats:
    return await service.get_stats()


@router.get(
    "/trend",
    summary="Registration trend: no filter = last 6 months; year = by month; year+month = by day",
)
async def get_trend(
    service: DashboardServiceDep,
    year: Annotated[int | None, Query(ge=2000, le=2100)] = None,
    month: Annotated[int | None, Query(ge=1, le=12)] = None,
) -> RegistrationTrend:
    return await service.get_trend(year, month)
