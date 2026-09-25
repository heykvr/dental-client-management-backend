import re
from datetime import date
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    StringConstraints,
    computed_field,
    model_validator,
)

from app.core.time import LocalDatetime, local_today
from app.schemas.common import optional_text

MAX_AGE_YEARS = 120
PHONE_PATTERN = re.compile(r"^\+?\d{10,15}$")

Gender = Literal["male", "female", "other"]


def calculate_age(date_of_birth: date, today: date | None = None) -> int:
    today = today or local_today()
    had_birthday = (today.month, today.day) >= (date_of_birth.month, date_of_birth.day)
    return today.year - date_of_birth.year - (0 if had_birthday else 1)


def _validate_date_of_birth(value: date) -> date:
    if value > local_today():
        raise ValueError("Date of birth cannot be in the future")
    if calculate_age(value) > MAX_AGE_YEARS:
        raise ValueError(f"Age cannot be more than {MAX_AGE_YEARS} years")
    return value


def _normalize_phone(value: str) -> str:
    # Accept common formats like "+91 98765-43210" or "(987) 654 3210"; store digits only
    cleaned = re.sub(r"[\s\-()]", "", value)
    if not PHONE_PATTERN.fullmatch(cleaned):
        raise ValueError("Phone must be 10-15 digits, optionally starting with +")
    return cleaned


FirstName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=50)]
LastName = optional_text(50)
DateOfBirth = Annotated[date, AfterValidator(_validate_date_of_birth)]
Phone = Annotated[str, StringConstraints(strip_whitespace=True), AfterValidator(_normalize_phone)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=300)]


class PatientCreate(BaseModel):
    """Body of POST /patients."""

    model_config = ConfigDict(extra="forbid")

    first_name: FirstName
    last_name: LastName = None
    date_of_birth: DateOfBirth
    gender: Gender
    phone: Phone
    address: Address


class PatientUpdate(BaseModel):
    """Body of PUT /patients/{id}. Send only the fields to change; patient_id cannot change."""

    model_config = ConfigDict(extra="forbid")

    first_name: FirstName | None = None
    last_name: LastName = None
    date_of_birth: DateOfBirth | None = None
    gender: Gender | None = None
    phone: Phone | None = None
    address: Address | None = None

    @model_validator(mode="after")
    def check_fields(self) -> "PatientUpdate":
        if not self.model_fields_set:
            raise ValueError("Provide at least one field to update")
        # Only last_name may be cleared; required fields cannot be set to null
        nulled = [
            name
            for name in self.model_fields_set
            if name != "last_name" and getattr(self, name) is None
        ]
        if nulled:
            raise ValueError(f"These fields cannot be empty: {', '.join(sorted(nulled))}")
        return self


class PatientResponse(BaseModel):
    """A patient as returned by the API. Mongo's _id is never exposed."""

    patient_id: str
    first_name: str
    last_name: str | None = None
    date_of_birth: date
    gender: Gender
    phone: str
    address: str
    created_at: LocalDatetime
    updated_at: LocalDatetime
    # From the embedded case sheet (status only, no clinical data): lets the list show
    # which patients still need a case sheet
    case_sheet_status: Literal["not_started", "pending", "completed"] = "not_started"
    case_sheet_updated_at: LocalDatetime | None = None

    @model_validator(mode="before")
    @classmethod
    def lift_case_sheet_status(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("case_sheet"), dict):
            sheet = data["case_sheet"]
            data = {
                **data,
                "case_sheet_status": sheet.get("status") or "not_started",
                "case_sheet_updated_at": sheet.get("updated_at"),
            }
        return data

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}" if self.last_name else self.first_name

    @computed_field
    @property
    def age(self) -> int:
        return calculate_age(self.date_of_birth)
