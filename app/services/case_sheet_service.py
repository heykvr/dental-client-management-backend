import hashlib
import json
from datetime import timedelta
from typing import Any

from app.core.exceptions import PatientNotFoundError
from app.core.time import utc_now
from app.repositories.case_sheet_repo import CaseSheetRepository
from app.schemas.case_sheet import (
    CaseSheetContent,
    CaseSheetInput,
    CaseSheetResponse,
    compute_status,
)
from app.services.patient_service import normalize_patient_id

# Patient fields the AI summary uses. Phone/address are left out: editing them
# does not change the clinical summary, so it should not become stale.
SUMMARY_PATIENT_FIELDS = ("first_name", "last_name", "date_of_birth", "gender")

# A "generating" summary older than this is reported as failed (see DECISIONS.md)
GENERATION_TIMEOUT = timedelta(minutes=2)


# Bump when prompts/summary.txt changes meaningfully: older summaries then show as outdated
# (with a Regenerate button) instead of "up to date". v2: added "Suggested next step".
SUMMARY_PROMPT_VERSION = 2


def summary_source_hash(patient: dict[str, Any], content: CaseSheetContent) -> str:
    """Fingerprint of everything the summary is based on (the data + the prompt version).
    Changes whenever that data or the summary prompt changes."""
    source = {
        "prompt_version": SUMMARY_PROMPT_VERSION,
        "patient": {field: patient.get(field) for field in SUMMARY_PATIENT_FIELDS},
        "case_sheet": content.model_dump(mode="json"),
    }
    encoded = json.dumps(source, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def summary_snapshot(doc: dict[str, Any]) -> dict[str, Any]:
    """The exact stored values the summary is based on, as a MongoDB filter. Used to save a
    summary only if none of them changed while the AI was working."""
    sheet = doc["case_sheet"]
    return {
        **{field: doc.get(field) for field in SUMMARY_PATIENT_FIELDS},
        **{
            f"case_sheet.{section}": sheet.get(section) for section in CaseSheetContent.model_fields
        },
    }


async def load_patient_with_case_sheet(
    case_sheets: CaseSheetRepository, patient_id: str
) -> dict[str, Any]:
    """Patient + embedded case sheet in one query; 404 if the patient doesn't exist."""
    doc = await case_sheets.get_patient_with_case_sheet(patient_id)
    if doc is None:
        raise PatientNotFoundError()
    if "case_sheet" not in doc:
        # Safety net: every patient is created with one
        await case_sheets.create_empty(patient_id)
        doc = await case_sheets.get_patient_with_case_sheet(patient_id)
    return doc


def to_case_sheet_response(doc: dict[str, Any]) -> CaseSheetResponse:
    sheet = doc["case_sheet"]
    summary = sheet.get("ai_summary") or {}
    saved_hash = summary.get("source_hash")
    current_hash = summary_source_hash(doc, CaseSheetContent.model_validate(sheet))
    is_stale = saved_hash is not None and saved_hash != current_hash
    state = summary.get("state")
    if state == "generating" and generation_is_stuck(summary):
        state = "failed"  # e.g. server restarted mid-generation; the UI offers Retry
    return CaseSheetResponse.model_validate(
        {
            **sheet,
            "patient_id": doc["patient_id"],
            "ai_summary": {**summary, "state": state, "is_stale": is_stale},
        }
    )


def generation_is_stuck(summary: dict[str, Any]) -> bool:
    requested_at = summary.get("requested_at")
    return requested_at is None or utc_now() - requested_at > GENERATION_TIMEOUT


class CaseSheetService:
    def __init__(self, case_sheets: CaseSheetRepository):
        self._case_sheets = case_sheets

    async def get_case_sheet(self, patient_id: str) -> CaseSheetResponse:
        doc = await load_patient_with_case_sheet(
            self._case_sheets, normalize_patient_id(patient_id)
        )
        return to_case_sheet_response(doc)

    async def save_case_sheet(self, patient_id: str, data: CaseSheetInput) -> CaseSheetResponse:
        patient_id = normalize_patient_id(patient_id)
        doc = await load_patient_with_case_sheet(self._case_sheets, patient_id)

        # Sections that were sent replace the stored ones; the rest stay as they are.
        # A section sent as null is cleared.
        merged = CaseSheetContent.model_validate(doc["case_sheet"])
        sent = {}
        for section in data.model_fields_set:
            value = getattr(data, section) or type(getattr(merged, section))()
            setattr(merged, section, value)
            sent[section] = value.model_dump()

        doc = await self._case_sheets.save(patient_id, sent, compute_status(merged))
        if doc is None:  # patient deleted in between
            raise PatientNotFoundError()
        return to_case_sheet_response(doc)
