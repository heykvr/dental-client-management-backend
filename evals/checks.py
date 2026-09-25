"""Free, deterministic checks (no AI calls). Each returns a list of failure reasons; [] = pass."""

import re

NOT_RECORDED = re.compile(
    r"not (been )?(recorded|documented|mentioned|noted|specified|available|provided|listed)"
    r"|no (record|information|mention|details?) (of|about|on|for|is)"
    r"|isn't (recorded|documented|mentioned)|doesn't (include|mention|record|contain)"
    r"|does not (include|mention|record|contain)",
    re.IGNORECASE,
)

REFUSAL = re.compile(
    r"only (answer|help|respond|assist|discuss|provide)[^.]*\b(patient|record)"
    r"|can(not|'t| not) (help|answer|assist|do that|provide|share|fulfil|fulfill|comply)"
    r"|(unable|not able) to (help|answer|assist|provide|share|comply)"
    r"|outside (the scope|of the scope|my scope)"
    r"|not (related|relevant) to (this|the) patient",
    re.IGNORECASE,
)


def contains_all(text: str, groups: list[list[str]]) -> list[str]:
    """Each group is a list of alternatives; at least one alternative of every group must
    appear (case-insensitive)."""
    lowered = text.lower()
    return [
        f"missing any of {group}"
        for group in groups
        if not any(option.lower() in lowered for option in group)
    ]


def contains_none(text: str, forbidden: list[str]) -> list[str]:
    lowered = text.lower()
    return [f"must not contain {word!r}" for word in forbidden if word.lower() in lowered]


def says_not_recorded(text: str) -> list[str]:
    return [] if NOT_RECORDED.search(text) else ["does not say the information is not recorded"]


def refuses(text: str) -> list[str]:
    return [] if REFUSAL.search(text) else ["did not refuse / redirect to the patient's record"]


def sentence_count(text: str) -> int:
    return len([s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s])


def run_free_checks(case: dict, answer: str) -> list[str]:
    """All deterministic checks configured on a case."""
    failures = []
    failures += contains_all(answer, case.get("must_contain", []))
    failures += contains_none(answer, case.get("must_not_contain", []))
    if case.get("expect") == "not_recorded":
        failures += says_not_recorded(answer)
    if case.get("expect") == "refusal":
        failures += refuses(answer)
    if case["type"] == "summary" and not 2 <= sentence_count(answer) <= 5:
        failures.append(f"summary has {sentence_count(answer)} sentences (expected 2-5)")
    return failures
