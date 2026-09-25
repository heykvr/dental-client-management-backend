from datetime import date

import pytest

from app.core.exceptions import AIUnavailableError, CaseSheetRequiredError, PatientNotFoundError
from app.repositories.case_sheet_repo import CaseSheetRepository
from app.repositories.patient_repo import PatientRepository
from app.services.summary_service import SummaryService

PATIENT = {
    "first_name": "Aarav",
    "last_name": "Ramesh",
    "date_of_birth": date(2002, 5, 14),
    "gender": "male",
    "phone": "+919876543210",
    "address": "12 MG Road, Bengaluru",
}
COMPLAINT = {"complaint": "Pain in lower right back tooth", "duration": "3 days"}


class FakeAI:
    """Stands in for AIClient: records calls, returns a canned answer or raises."""

    model = "fake-gemini"

    def __init__(self, text="Patient reports pain in the lower right back tooth.", error=None):
        self.text, self.error, self.calls = text, error, []
        self.during_call = None  # optional coroutine factory run mid-generation

    async def generate(self, *, system, contents, max_output_tokens):
        self.calls.append({"system": system, "contents": contents})
        if self.during_call:
            await self.during_call()
        if self.error:
            raise self.error
        return self.text


@pytest.fixture
async def repo(db):
    await PatientRepository(db).create("PAT-0001", PATIENT)
    return CaseSheetRepository(db)


async def fill_complaint(repo):
    await repo.save("PAT-0001", {"chief_complaint": COMPLAINT}, "pending")


async def test_generates_and_saves_summary(repo):
    await fill_complaint(repo)
    ai = FakeAI()

    sheet = await SummaryService(repo, ai).generate("pat-0001")

    assert sheet.ai_summary.text == ai.text
    assert sheet.ai_summary.state == "ready"
    assert sheet.ai_summary.model == "fake-gemini"
    assert sheet.ai_summary.generated_at is not None
    assert sheet.ai_summary.is_stale is False


async def test_prompt_contains_the_record_and_summary_rules(repo):
    await fill_complaint(repo)
    ai = FakeAI()

    await SummaryService(repo, ai).generate("PAT-0001")

    assert "Pain in lower right back tooth" in ai.calls[0]["contents"]
    assert "- Diagnosis: Not recorded" in ai.calls[0]["contents"]
    assert "Never add findings" in ai.calls[0]["system"]


async def test_summary_becomes_stale_after_an_edit(repo):
    await fill_complaint(repo)
    await SummaryService(repo, FakeAI()).generate("PAT-0001")

    await repo.save("PAT-0001", {"diagnosis": {"diagnosis": "Caries", "notes": None}}, "pending")
    doc = await repo.get_patient_with_case_sheet("PAT-0001")

    from app.services.case_sheet_service import to_case_sheet_response

    assert to_case_sheet_response(doc).ai_summary.is_stale is True


async def test_edit_during_generation_discards_the_older_summary(repo):
    await fill_complaint(repo)
    ai = FakeAI(text="Summary of the OLD record")

    async def dentist_edits_meanwhile():
        await repo.save(
            "PAT-0001", {"diagnosis": {"diagnosis": "Caries", "notes": None}}, "pending"
        )

    ai.during_call = dentist_edits_meanwhile

    sheet = await SummaryService(repo, ai).generate("PAT-0001")

    assert sheet.ai_summary.text is None  # the older result was not saved
    assert sheet.diagnosis.diagnosis == "Caries"


async def test_patient_edit_that_is_not_summarised_does_not_discard(repo):
    await fill_complaint(repo)
    ai = FakeAI()

    async def phone_changes_meanwhile():
        await PatientRepository(repo._collection.database).update(
            "PAT-0001", {"phone": "+911111111111"}
        )

    ai.during_call = phone_changes_meanwhile

    sheet = await SummaryService(repo, ai).generate("PAT-0001")

    assert sheet.ai_summary.text == ai.text  # phone isn't part of the summary


async def test_ai_failure_marks_failed_and_keeps_previous_summary(repo):
    await fill_complaint(repo)
    await SummaryService(repo, FakeAI(text="First summary")).generate("PAT-0001")
    await repo.save("PAT-0001", {"diagnosis": {"diagnosis": "Caries", "notes": None}}, "pending")

    with pytest.raises(AIUnavailableError):
        await SummaryService(repo, FakeAI(error=AIUnavailableError())).generate("PAT-0001")

    doc = await repo.get_patient_with_case_sheet("PAT-0001")
    summary = doc["case_sheet"]["ai_summary"]
    assert summary["state"] == "failed"
    assert summary["text"] == "First summary"


async def test_not_started_sheet_is_rejected_without_calling_ai(repo):
    ai = FakeAI()

    with pytest.raises(CaseSheetRequiredError):
        await SummaryService(repo, ai).generate("PAT-0001")

    assert ai.calls == []


async def test_unknown_patient_is_404(repo):
    with pytest.raises(PatientNotFoundError):
        await SummaryService(repo, FakeAI()).generate("PAT-9999")
