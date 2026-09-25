import logging
from typing import Any

from app.core.config import get_settings
from app.core.exceptions import AIUnavailableError, AppError, CaseSheetRequiredError
from app.core.time import utc_now
from app.repositories.case_sheet_repo import CaseSheetRepository
from app.schemas.case_sheet import CaseSheetContent, CaseSheetResponse
from app.services.ai_service import AIClient, format_patient_record, load_prompt
from app.services.case_sheet_service import (
    generation_is_stuck,
    load_patient_with_case_sheet,
    summary_snapshot,
    summary_source_hash,
    to_case_sheet_response,
)
from app.services.patient_service import normalize_patient_id

logger = logging.getLogger(__name__)

SUMMARY_MAX_OUTPUT_TOKENS = 350  # summary + "Suggested next step" line


class SummaryService:
    def __init__(self, case_sheets: CaseSheetRepository, ai: AIClient):
        self._case_sheets = case_sheets
        self._ai = ai

    async def generate(self, patient_id: str) -> CaseSheetResponse:
        """Write a new AI summary of the patient's record and save it, unless the record
        changed while the AI was working (then the newer edit wins and this result is dropped).
        If the saved summary already matches the record, it is returned without calling the AI.
        """
        patient_id = normalize_patient_id(patient_id)
        doc = await load_patient_with_case_sheet(self._case_sheets, patient_id)
        if doc["case_sheet"]["status"] == "not_started":
            raise CaseSheetRequiredError()

        snapshot = summary_snapshot(doc)
        source_hash = summary_source_hash(doc, CaseSheetContent.model_validate(doc["case_sheet"]))
        current = doc["case_sheet"].get("ai_summary") or {}
        if current.get("state") == "ready" and current.get("source_hash") == source_hash:
            # Up to date: nothing changed since this summary was written, so no AI call
            return to_case_sheet_response(doc)

        try:
            text = await self._ai.generate(
                system=load_prompt("summary"),
                contents=format_patient_record(doc),
                max_output_tokens=SUMMARY_MAX_OUTPUT_TOKENS,
                timeout_seconds=get_settings().ai_summary_timeout_seconds,
            )
        except AIUnavailableError:
            # Keep the previous summary text; the UI shows "Couldn't update summary, Retry"
            await self._case_sheets.set_summary_state_if_unchanged(patient_id, snapshot, "failed")
            raise

        summary = {
            "text": text,
            "generated_at": utc_now(),
            "model": self._ai.model,
            "source_hash": source_hash,
            "state": "ready",
        }
        saved = await self._case_sheets.set_summary_if_unchanged(patient_id, snapshot, summary)
        if not saved:
            logger.info("Summary for %s discarded: record changed during generation", patient_id)

        doc = await load_patient_with_case_sheet(self._case_sheets, patient_id)
        return to_case_sheet_response(doc)

    # ------------------------------------------------------------ automatic regeneration

    @staticmethod
    def needs_regeneration(doc: dict[str, Any]) -> str | None:
        """Fingerprint of the current content if a new summary should be generated, else None.

        Needed when the sheet has some data and the summarised content differs from what the
        current summary was made from, unless a generation for this exact content is already
        running (saving the same content twice must not start a second one).
        """
        sheet = doc.get("case_sheet") or {}
        if sheet.get("status", "not_started") == "not_started":
            return None
        current = summary_source_hash(doc, CaseSheetContent.model_validate(sheet))
        summary = sheet.get("ai_summary") or {}
        if current == summary.get("source_hash"):
            return None
        already_running = (
            summary.get("state") == "generating"
            and summary.get("requested_hash") == current
            and not generation_is_stuck(summary)
        )
        return None if already_running else current

    async def pending_refresh(self, patient_id: str) -> str | None:
        """Loads the patient (one query) and returns the fingerprint to generate for, if any."""
        doc = await load_patient_with_case_sheet(
            self._case_sheets, normalize_patient_id(patient_id)
        )
        return self.needs_regeneration(doc)

    async def mark_generating(self, patient_id: str, requested_hash: str) -> None:
        await self._case_sheets.mark_generating(normalize_patient_id(patient_id), requested_hash)

    async def generate_in_background(self, patient_id: str) -> None:
        """Background-task entry point: never raises. Failures are already recorded on the
        summary (state "failed") and logged, and the user can press Retry."""
        try:
            await self.generate(patient_id)
        except AppError as exc:
            logger.info("Background summary for %s not generated: %s", patient_id, exc.code)
        except Exception:
            logger.exception("Background summary for %s crashed", patient_id)
