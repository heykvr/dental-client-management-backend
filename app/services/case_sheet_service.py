import hashlib
import json
from typing import Any

from app.core.exceptions import PatientNotFoundError
from app.repositories.case_sheet_repo import CaseSheetRepository
from app.repositories.patient_repo import PatientRepository
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


def summary_source_hash(patient: dict[str, Any], content: CaseSheetContent) -> str:
    """Fingerprint of everything the summary is based on. Changes whenever that data changes."""
    source = {
        "patient": {field: patient.get(field) for field in SUMMARY_PATIENT_FIELDS},
        "case_sheet": content.model_dump(mode="json"),
    }
    encoded = json.dumps(source, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


class CaseSheetService:
    def __init__(self, case_sheets: CaseSheetRepository, patients: PatientRepository):
        self._case_sheets = case_sheets
        self._patients = patients

    async def get_case_sheet(self, patient_id: str) -> CaseSheetResponse:
        patient_id = normalize_patient_id(patient_id)
        patient = await self._require_patient(patient_id)
        doc = await self._case_sheets.get(patient_id)
        if doc is None:
            # Safety net: every patient should already have one (created with the patient)
            await self._case_sheets.create_empty(patient_id)
            doc = await self._case_sheets.get(patient_id)
        return self._to_response(doc, patient)

    async def save_case_sheet(self, patient_id: str, data: CaseSheetInput) -> CaseSheetResponse:
        patient_id = normalize_patient_id(patient_id)
        patient = await self._require_patient(patient_id)
        current = await self._case_sheets.get(patient_id) or {}

        # Sections that were sent replace the stored ones; the rest stay as they are.
        # A section sent as null is cleared.
        merged = CaseSheetContent.model_validate(current)
        sent = {}
        for section in data.model_fields_set:
            value = getattr(data, section) or type(getattr(merged, section))()
            setattr(merged, section, value)
            sent[section] = value.model_dump()

        doc = await self._case_sheets.save(patient_id, sent, compute_status(merged))
        return self._to_response(doc, patient)

    async def _require_patient(self, patient_id: str) -> dict[str, Any]:
        patient = await self._patients.get(patient_id)
        if patient is None:
            raise PatientNotFoundError()
        return patient

    @staticmethod
    def _to_response(doc: dict[str, Any], patient: dict[str, Any]) -> CaseSheetResponse:
        summary = doc.get("ai_summary") or {}
        saved_hash = summary.get("source_hash")
        current_hash = summary_source_hash(patient, CaseSheetContent.model_validate(doc))
        is_stale = saved_hash is not None and saved_hash != current_hash
        return CaseSheetResponse.model_validate(
            {**doc, "ai_summary": {**summary, "is_stale": is_stale}}
        )
