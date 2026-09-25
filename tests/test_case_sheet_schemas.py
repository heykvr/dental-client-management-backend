import pytest
from pydantic import ValidationError

from app.schemas.case_sheet import CaseSheetContent, CaseSheetInput, compute_status

COMPLETE = {
    "chief_complaint": {"complaint": "Pain in lower right back tooth"},
    "investigation": {
        "tooth_area": "46 - Lower Right First Molar",
        "clinical_findings": "Deep dental caries observed",
        "tenderness": True,
    },
    "diagnosis": {"diagnosis": "Deep dental caries with suspected pulpal involvement"},
}


def status_of(data: dict) -> str:
    return compute_status(CaseSheetContent.model_validate(data))


def test_empty_sheet_is_not_started():
    assert status_of({}) == "not_started"


def test_only_chief_complaint_is_pending():
    assert status_of({"chief_complaint": {"complaint": "Tooth pain"}}) == "pending"


def test_only_optional_field_is_pending():
    assert status_of({"diagnosis": {"notes": "Call back next week"}}) == "pending"


def test_all_required_fields_is_completed_without_optional_ones():
    # duration, sensitivity, additional_findings and notes are optional
    assert status_of(COMPLETE) == "completed"


def test_tenderness_false_counts_as_answered():
    data = {**COMPLETE, "investigation": {**COMPLETE["investigation"], "tenderness": False}}

    assert status_of(data) == "completed"


@pytest.mark.parametrize(
    ("section", "field"),
    [
        ("chief_complaint", "complaint"),
        ("investigation", "tooth_area"),
        ("investigation", "clinical_findings"),
        ("investigation", "tenderness"),
        ("diagnosis", "diagnosis"),
    ],
)
def test_missing_any_required_field_is_pending(section, field):
    data = {**COMPLETE, section: {**COMPLETE[section], field: None}}

    assert status_of(data) == "pending"


def test_blank_text_becomes_none():
    sheet = CaseSheetInput.model_validate({"chief_complaint": {"complaint": "   "}})

    assert sheet.chief_complaint.complaint is None


def test_input_sections_are_optional():
    sheet = CaseSheetInput.model_validate({"diagnosis": {"diagnosis": "Caries"}})

    assert sheet.chief_complaint is None
    assert sheet.investigation is None
    assert sheet.model_fields_set == {"diagnosis"}
    assert sheet.diagnosis.model_dump() == {"diagnosis": "Caries", "notes": None}


@pytest.mark.parametrize(
    "data",
    [
        {"chief_complaint": {"complaint": "x" * 1001}},
        {"investigation": {"tenderness": "maybe"}},
        {"diagnosis": {"unknown_field": "x"}},
        {"status": "completed"},  # status is computed by the server, never accepted
    ],
)
def test_invalid_input_is_rejected(data):
    with pytest.raises(ValidationError):
        CaseSheetInput.model_validate(data)
