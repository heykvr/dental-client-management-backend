from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.core.time import LocalDatetime
from app.schemas.common import optional_text

CaseSheetStatus = Literal["not_started", "pending", "completed"]
SummaryState = Literal["generating", "ready", "failed"]


# Every field is optional so partial drafts can be saved. Blank text becomes None.
class ChiefComplaint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    complaint: optional_text(1000) = None
    duration: optional_text(100) = None


class Investigation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tooth_area: optional_text(200) = None
    clinical_findings: optional_text(1000) = None
    tenderness: bool | None = None
    sensitivity: optional_text(500) = None
    additional_findings: optional_text(1000) = None


class Diagnosis(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diagnosis: optional_text(1000) = None
    notes: optional_text(1000) = None


class CaseSheetContent(BaseModel):
    """The clinical part of a case sheet (all three sections)."""

    chief_complaint: ChiefComplaint = ChiefComplaint()
    investigation: Investigation = Investigation()
    diagnosis: Diagnosis = Diagnosis()


class CaseSheetInput(BaseModel):
    """Body of PUT /patients/{id}/case-sheet. A section that is sent replaces the stored one;
    a section that is left out stays unchanged, so each section can be saved on its own."""

    model_config = ConfigDict(extra="forbid")

    chief_complaint: ChiefComplaint | None = None
    investigation: Investigation | None = None
    diagnosis: Diagnosis | None = None


# Fields that must be filled for the case sheet to count as completed
REQUIRED_FOR_COMPLETION = [
    ("chief_complaint", "complaint"),
    ("investigation", "tooth_area"),
    ("investigation", "clinical_findings"),
    ("investigation", "tenderness"),
    ("diagnosis", "diagnosis"),
]


def compute_status(content: CaseSheetContent) -> CaseSheetStatus:
    # "is not None" so tenderness=False ("No") counts as an answer
    values = [
        value
        for section in (content.chief_complaint, content.investigation, content.diagnosis)
        for value in section.model_dump().values()
    ]
    if all(value is None for value in values):
        return "not_started"
    required = [getattr(getattr(content, s), f) for s, f in REQUIRED_FOR_COMPLETION]
    return "completed" if all(value is not None for value in required) else "pending"


class AiSummaryResponse(BaseModel):
    text: str | None = None
    generated_at: LocalDatetime | None = None
    model: str | None = None
    state: SummaryState | None = None
    is_stale: bool = False


class CaseSheetResponse(CaseSheetContent):
    patient_id: str
    status: CaseSheetStatus
    ai_summary: AiSummaryResponse = AiSummaryResponse()
    created_at: LocalDatetime
    updated_at: LocalDatetime
