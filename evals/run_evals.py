"""AI evals: 30 synthetic cases for the summary and chatbot, 15 graded by a judge model.

Run from the backend folder (uses GEMINI_API_KEY, AI_MODEL, EVAL_JUDGE_MODEL from .env):

    uv run python -m evals.run_evals            # resumes: only runs cases not done yet
    uv run python -m evals.run_evals --fresh    # start over

Calls the SAME prompt-building code and AI client as the app (no HTTP, no database), paces
requests to stay inside the Gemini free tier, saves every result as it goes, and writes
evals/reports/latest.md.
"""

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.exceptions import AIUnavailableError
from app.core.time import app_tz
from app.schemas.chat import ChatRequest
from app.services.ai_service import format_patient_record, get_ai_client, load_prompt
from app.services.chat_service import CHAT_MAX_OUTPUT_TOKENS, build_chat_prompt
from app.services.summary_service import SUMMARY_MAX_OUTPUT_TOKENS
from evals.checks import run_free_checks

EVALS_DIR = Path(__file__).resolve().parent
DATASET = EVALS_DIR / "dataset.json"
RESULTS = EVALS_DIR / "results" / "latest.jsonl"
REPORT = EVALS_DIR / "reports" / "latest.md"

# Free tier: app model 15 RPM, judge model 5 RPM (see DECISIONS.md). Stay a little under.
APP_MIN_INTERVAL_S = 4.5
JUDGE_MIN_INTERVAL_S = 13.0
JUDGE_TIMEOUT_MS = 60_000  # the judge isn't user-facing, so it can take its time


class JudgeVerdict(BaseModel):
    faithful: bool
    invented_facts: list[str]
    follows_rules: bool
    reason: str


class Pacer:
    """Keeps at least `interval` seconds between calls to one model."""

    def __init__(self, interval: float):
        self.interval, self._last = interval, 0.0

    async def wait(self) -> None:
        delay = self._last + self.interval - time.monotonic()
        if delay > 0:
            await asyncio.sleep(delay)
        self._last = time.monotonic()


def patient_doc(patient_id: str, patient: dict) -> dict:
    """Same shape as a patient document in MongoDB (case sheet embedded)."""
    fields = ("first_name", "last_name", "date_of_birth", "gender", "case_sheet")
    return {"patient_id": patient_id, **{field: patient.get(field) for field in fields}}


async def ask_app(ai, case: dict, doc: dict) -> str:
    if case["type"] == "summary":
        return await ai.generate(
            system=load_prompt("summary"),
            contents=format_patient_record(doc),
            max_output_tokens=SUMMARY_MAX_OUTPUT_TOKENS,
        )
    system, contents = build_chat_prompt(doc, ChatRequest(message=case["message"]))
    return await ai.generate(
        system=system, contents=contents, max_output_tokens=CHAT_MAX_OUTPUT_TOKENS
    )


async def ask_judge(client: genai.Client, model: str, case: dict, doc: dict, answer: str):
    task = (
        "Write a short clinical summary of the record."
        if case["type"] == "summary"
        else f"Answer the dentist's question: {case['message']}"
    )
    response = await client.aio.models.generate_content(
        model=model,
        contents=f"{format_patient_record(doc)}\n\nTASK: {task}\n\nANSWER TO GRADE:\n{answer}",
        config=types.GenerateContentConfig(
            system_instruction=(EVALS_DIR / "judge_prompt.txt").read_text(encoding="utf-8"),
            temperature=0,
            response_mime_type="application/json",
            response_schema=JudgeVerdict,
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        ),
    )
    return JudgeVerdict.model_validate_json(response.text)


def load_results(fresh: bool) -> dict[str, dict]:
    if fresh or not RESULTS.exists():
        return {}
    lines = RESULTS.read_text(encoding="utf-8").splitlines()
    return {row["id"]: row for row in map(json.loads, lines) if row}


def save_results(results: dict[str, dict]) -> None:
    RESULTS.parent.mkdir(parents=True, exist_ok=True)
    RESULTS.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in results.values()),
        encoding="utf-8",
    )


def is_done(row: dict | None) -> bool:
    if not row or row.get("error"):
        return False
    return row["grader"] == "free" or row.get("verdict") is not None


async def run(fresh: bool) -> dict[str, dict]:
    settings = get_settings()
    dataset = json.loads(DATASET.read_text(encoding="utf-8"))
    ai = get_ai_client()
    judge = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(
            timeout=JUDGE_TIMEOUT_MS,
            retry_options=types.HttpRetryOptions(
                attempts=2, http_status_codes=[500, 502, 503, 504]
            ),
        ),
    )
    app_pacer, judge_pacer = Pacer(APP_MIN_INTERVAL_S), Pacer(JUDGE_MIN_INTERVAL_S)
    results = load_results(fresh)

    for number, case in enumerate(dataset["cases"], start=1):
        previous = results.get(case["id"])
        if is_done(previous):
            continue
        doc = patient_doc(case["patient"], dataset["patients"][case["patient"]])
        row = {
            "id": case["id"],
            "category": case["category"],
            "grader": case["grader"],
            "patient": case["patient"],
            "question": case.get("message", "(summary)"),
            "model": ai.model,
            "judge_model": settings.eval_judge_model,
        }
        # Reuse an answer from an interrupted run; only the judge step is missing then
        if previous and previous.get("answer") and previous.get("model") == ai.model:
            row.update(answer=previous["answer"], latency_s=previous["latency_s"])
        else:
            await app_pacer.wait()
            started = time.monotonic()
            try:
                row["answer"] = await ask_app(ai, case, doc)
            except AIUnavailableError:
                row["error"] = "app model unavailable (timeout, quota or overload)"
            row["latency_s"] = round(time.monotonic() - started, 2)

        if "answer" in row:
            row["free_failures"] = run_free_checks(case, row["answer"])
            if case["grader"] == "judge":
                await judge_pacer.wait()
                try:
                    verdict = await ask_judge(
                        judge, settings.eval_judge_model, case, doc, row["answer"]
                    )
                    row["verdict"] = verdict.model_dump()
                except Exception as exc:  # judge quota, overload, bad JSON
                    row["error"] = f"judge failed: {type(exc).__name__}: {str(exc)[:160]}"

        verdict = row.get("verdict")
        row["passed"] = (
            not row.get("error")
            and not row.get("free_failures")
            and (case["grader"] == "free" or (verdict["faithful"] and verdict["follows_rules"]))
        )
        results[case["id"]] = row
        save_results(results)
        status = "PASS" if row["passed"] else ("ERROR" if row.get("error") else "FAIL")
        print(f"[{number:2}/{len(dataset['cases'])}] {case['id']:7} {status}", flush=True)

    return results


def write_report(results: dict[str, dict]) -> str:
    rows = list(results.values())
    categories = [
        "summary", "summarize", "explain", "retrieval", "missing", "out_of_scope", "injection"
    ]  # fmt: skip
    latencies = [r["latency_s"] for r in rows if r.get("answer")]
    invented = sum(len((r.get("verdict") or {}).get("invented_facts", [])) for r in rows)
    judged = [r for r in rows if r.get("verdict")]
    passed = sum(r["passed"] for r in rows)
    first = rows[0] if rows else {}
    p50 = f"{statistics.median(latencies):.2f} s" if latencies else "n/a"

    lines = [
        "# AI eval report",
        "",
        f"- Run: {datetime.now(app_tz()):%Y-%m-%d %H:%M} IST",
        f"- App model: `{first.get('model')}` · Judge model: `{first.get('judge_model')}`",
        f"- **Passed: {passed}/{len(rows)}** · Judged: {len(judged)} · "
        f"**Invented facts: {invented}** · p50 latency: {p50}",
        "",
        "| Category | Graded by | Passed |",
        "|---|---|---|",
    ]
    for category in categories:
        group = [r for r in rows if r["category"] == category]
        if group:
            grader = "judge" if group[0]["grader"] == "judge" else "free checks"
            lines.append(
                f"| {category} | {grader} | {sum(r['passed'] for r in group)}/{len(group)} |"
            )

    failed = [r for r in rows if not r["passed"]]
    lines += ["", "## Failed or errored cases", ""] if failed else ["", "All cases passed.", ""]
    for r in failed:
        reasons = list(r.get("free_failures") or [])
        if r.get("verdict"):
            v = r["verdict"]
            reasons += [f"judge: {v['reason']}"] + [f"invented: {f}" for f in v["invented_facts"]]
        if r.get("error"):
            reasons.append(r["error"])
        answer = (r.get("answer") or "").replace("\n", " ")[:400]
        lines += [
            f"### {r['id']} ({r['category']}, {r['patient']})",
            f"- Question: {r['question']}",
            f"- Answer: {answer or '(none)'}",
            *[f"- {reason}" for reason in reasons],
            "",
        ]

    report = "\n".join(lines)
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(report, encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AI evals")
    parser.add_argument("--fresh", action="store_true", help="ignore saved results, start over")
    args = parser.parse_args()
    results = asyncio.run(run(args.fresh))
    print("\n" + write_report(results))
    print(f"\nReport written to {REPORT.relative_to(EVALS_DIR.parent)}")


if __name__ == "__main__":
    main()
