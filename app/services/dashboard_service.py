import asyncio
import calendar
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta

from app.core.exceptions import InvalidRequestError
from app.core.time import app_tz, utc_now
from app.repositories.case_sheet_repo import CaseSheetRepository
from app.repositories.patient_repo import PatientRepository
from app.schemas.dashboard import DashboardStats, RegistrationTrend, TrendPoint
from app.schemas.patient import PatientResponse

DEFAULT_TREND_MONTHS = 6
RECENT_PATIENTS = 5


def _add_months(day: date, months: int) -> date:
    """First day of the month `months` away from `day`'s month."""
    index = day.year * 12 + (day.month - 1) + months
    return date(index // 12, index % 12 + 1, 1)


class DashboardService:
    def __init__(
        self,
        patients: PatientRepository,
        case_sheets: CaseSheetRepository,
        clock: Callable[[], datetime] = utc_now,
    ):
        self._patients = patients
        self._case_sheets = case_sheets
        self._clock = clock  # injectable so tests can fix "now"

    def _local_today(self) -> date:
        return self._clock().astimezone(app_tz()).date()

    def _to_utc(self, day: date) -> datetime:
        """Midnight at the start of `day` in the app timezone, as a UTC datetime."""
        return datetime.combine(day, time(), tzinfo=app_tz()).astimezone(UTC)

    async def get_stats(self) -> DashboardStats:
        month_start = self._local_today().replace(day=1)
        # Independent queries run at the same time: the page waits for the slowest one,
        # not for the sum of all of them
        statuses, (recent, total), new_this_month, trend = await asyncio.gather(
            self._case_sheets.count_by_status(),
            self._patients.list(None, skip=0, limit=RECENT_PATIENTS),
            self._patients.count(self._to_utc(month_start)),
            self.get_trend(),
        )
        return DashboardStats(
            total_patients=total,
            new_patients_this_month=new_this_month,
            completed_case_sheets=statuses.get("completed", 0),
            # A patient without a case sheet (shouldn't happen) counts as not started
            pending_case_sheets=statuses.get("pending", 0)
            + statuses.get("not_started", 0)
            + statuses.get(None, 0),
            registration_trend=trend,
            recent_patients=[PatientResponse.model_validate(doc) for doc in recent],
        )

    async def get_trend(
        self, year: int | None = None, month: int | None = None
    ) -> RegistrationTrend:
        if month is not None and year is None:
            raise InvalidRequestError("Choose a year when filtering by month.")

        if year is not None and month is not None:
            # One point per day of the chosen month
            start = date(year, month, 1)
            days = calendar.monthrange(year, month)[1]
            periods = [(start + timedelta(days=n)).isoformat() for n in range(days)]
            end, date_format, granularity = _add_months(start, 1), "%Y-%m-%d", "day"
        else:
            # One point per month: the chosen year, or the last N months up to now
            if year is not None:
                start, count = date(year, 1, 1), 12
            else:
                count = DEFAULT_TREND_MONTHS
                start = _add_months(self._local_today(), -(count - 1))
            months = [_add_months(start, n) for n in range(count)]
            periods = [m.strftime("%Y-%m") for m in months]
            end, date_format, granularity = _add_months(start, count), "%Y-%m", "month"

        counts = await self._patients.registrations_by_period(
            self._to_utc(start), self._to_utc(end), date_format, app_tz().key
        )
        return RegistrationTrend(
            granularity=granularity,
            points=[TrendPoint(period=p, count=counts.get(p, 0)) for p in periods],
        )
