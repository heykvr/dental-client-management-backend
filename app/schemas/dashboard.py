from typing import Literal

from pydantic import BaseModel

from app.schemas.patient import PatientResponse


class TrendPoint(BaseModel):
    period: str  # "2026-09" (month) or "2026-09-05" (day), in the app timezone
    count: int


class RegistrationTrend(BaseModel):
    granularity: Literal["month", "day"]
    points: list[TrendPoint]


class DashboardStats(BaseModel):
    total_patients: int
    new_patients_this_month: int
    completed_case_sheets: int
    pending_case_sheets: int  # pending + not_started
    registration_trend: RegistrationTrend
    recent_patients: list[PatientResponse]
