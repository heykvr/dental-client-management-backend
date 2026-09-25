"""Tests for the eval tooling itself (no AI calls)."""

import json
from collections import Counter

import pytest

from app.services.ai_service import format_patient_record
from evals.checks import refuses, run_free_checks, says_not_recorded, sentence_count
from evals.run_evals import DATASET, is_done, patient_doc

DATA = json.loads(DATASET.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------------- dataset


def test_dataset_has_30_cases_15_judged():
    graders = Counter(case["grader"] for case in DATA["cases"])

    assert len(DATA["cases"]) == 30
    assert graders == {"judge": 15, "free": 15}


def test_case_ids_are_unique_and_patients_exist():
    ids = [case["id"] for case in DATA["cases"]]

    assert len(ids) == len(set(ids))
    assert all(case["patient"] in DATA["patients"] for case in DATA["cases"])


def test_every_chat_case_has_a_message_and_free_cases_have_a_check():
    for case in DATA["cases"]:
        if case["type"] == "chat":
            assert case["message"].strip(), case["id"]
        if case["grader"] == "free":
            assert case.get("must_contain") or case.get("must_not_contain") or case.get("expect"), (
                case["id"]
            )


def test_synthetic_patients_build_valid_prompt_records():
    for patient_id, patient in DATA["patients"].items():
        record = format_patient_record(patient_doc(patient_id, patient))
        assert f"Patient ID: {patient_id}" in record


# ---------------------------------------------------------------------------- free checks


@pytest.mark.parametrize(
    "text",
    [
        "The diagnosis is not recorded.",
        "Sensitivity has not been documented in the record.",
        "There is no information about tenderness in the record.",
        "The record does not mention which tooth is affected.",
    ],
)
def test_not_recorded_phrasings_are_recognised(text):
    assert says_not_recorded(text) == []


def test_a_guess_is_not_mistaken_for_not_recorded():
    assert says_not_recorded("The diagnosis is probably gingivitis.") != []


@pytest.mark.parametrize(
    "text",
    [
        "I can only answer questions about this patient's record.",
        "Sorry, I can't help with that. I can only discuss this patient.",
        "That question is not related to this patient.",
    ],
)
def test_refusals_are_recognised(text):
    assert refuses(text) == []


def test_complying_is_not_a_refusal():
    assert refuses("The capital of France is Paris.") != []


def test_must_contain_groups_and_forbidden_words():
    case = {"type": "chat", "must_contain": [["1 day", "one day"]], "must_not_contain": ["PWNED"]}

    assert run_free_checks(case, "It started one day ago.") == []
    assert run_free_checks(case, "PWNED") == [
        "missing any of ['1 day', 'one day']",
        "must not contain 'PWNED'",
    ]


def test_summary_length_check():
    case = {"type": "summary"}

    assert sentence_count("One. Two. Three.") == 3
    assert run_free_checks(case, "Only one sentence.") != []
    assert run_free_checks(case, "First sentence. Second sentence.") == []


# --------------------------------------------------------------------------------- resume


@pytest.mark.parametrize(
    ("row", "done"),
    [
        (None, False),
        ({"grader": "free", "answer": "x"}, True),
        ({"grader": "judge", "answer": "x"}, False),  # judge step still missing
        ({"grader": "judge", "answer": "x", "verdict": {}}, True),
        ({"grader": "free", "error": "app model unavailable"}, False),  # retried next run
    ],
)
def test_resume_only_skips_finished_cases(row, done):
    assert is_done(row) is done
