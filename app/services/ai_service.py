"""Everything that talks to the AI provider (Google Gemini) lives here.

The rest of the app only calls `AIClient.generate()` with a prompt; the provider, model,
timeout, retries and error handling stay in this file (see DECISIONS.md).
"""

import asyncio
import logging
from datetime import date
from functools import cache, lru_cache
from pathlib import Path
from typing import Any

import httpx
from google import genai
from google.genai import errors, types

from app.core.config import get_settings
from app.core.exceptions import AIUnavailableError
from app.schemas.patient import calculate_age

logger = logging.getLogger(__name__)

PROMPTS_DIR = Path(__file__).resolve().parent.parent / "prompts"
NOT_RECORDED = "Not recorded"
RECORD_TAG = "patient_record"
GOOGLE_MIN_DEADLINE_MS = 10_000  # Gemini API rejects shorter request deadlines


@cache
def load_prompt(name: str) -> str:
    """Prompt text from app/prompts/<name>.txt (kept out of code so it is easy to review)."""
    return (PROMPTS_DIR / f"{name}.txt").read_text(encoding="utf-8").strip()


# ---------------------------------------------------------------- patient record for prompts


def _value(value: Any) -> str:
    """Empty fields are written as "Not recorded" (never omitted), so the model can't mistake
    a gap for data. The record's closing tag is neutralised so record text can't break out of
    the data block (prompt-injection safety)."""
    if value is None or (isinstance(value, str) and not value.strip()):
        return NOT_RECORDED
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value).strip().replace(f"</{RECORD_TAG}>", f"</ {RECORD_TAG}>")


def format_patient_record(doc: dict[str, Any]) -> str:
    """The patient's clinical record as plain text, wrapped in <patient_record> tags.

    Uses the fields the summary is based on (name, age, gender + case sheet). Phone and
    address are left out on purpose: they are not clinical and don't belong in the prompt.
    """
    sheet = doc.get("case_sheet") or {}
    complaint = sheet.get("chief_complaint") or {}
    investigation = sheet.get("investigation") or {}
    diagnosis = sheet.get("diagnosis") or {}

    name = " ".join(p for p in (doc.get("first_name"), doc.get("last_name")) if p)
    dob = doc.get("date_of_birth")
    age = f"{calculate_age(date.fromisoformat(dob))} years" if dob else NOT_RECORDED

    lines = [
        f"<{RECORD_TAG}>",
        f"Patient ID: {_value(doc.get('patient_id'))}",
        f"Name: {_value(name)}",
        f"Age: {age}",
        f"Gender: {_value(doc.get('gender'))}",
        "",
        "Chief complaint",
        f"- Complaint: {_value(complaint.get('complaint'))}",
        f"- Duration: {_value(complaint.get('duration'))}",
        "",
        "Investigation",
        f"- Tooth / area: {_value(investigation.get('tooth_area'))}",
        f"- Clinical findings: {_value(investigation.get('clinical_findings'))}",
        f"- Tenderness: {_value(investigation.get('tenderness'))}",
        f"- Sensitivity: {_value(investigation.get('sensitivity'))}",
        f"- Additional findings: {_value(investigation.get('additional_findings'))}",
        "",
        "Diagnosis",
        f"- Diagnosis: {_value(diagnosis.get('diagnosis'))}",
        f"- Notes: {_value(diagnosis.get('notes'))}",
        f"</{RECORD_TAG}>",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------- Gemini client


class AIClient:
    """Thin wrapper around the Gemini SDK. Every failure becomes AIUnavailableError (503)."""

    def __init__(self, client: genai.Client, model: str, timeout_seconds: float):
        self._client = client
        self.model = model
        self._timeout_seconds = timeout_seconds

    async def generate(
        self,
        *,
        system: str,
        contents: str | list[types.Content],
        max_output_tokens: int = 400,
    ) -> str:
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.2,  # factual, low-variance answers
            max_output_tokens=max_output_tokens,
            # Short grounded answers don't need long reasoning; keeps us inside the 5 s timeout
            thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel.MINIMAL),
            # We never give the model tools; skip the SDK's function-calling machinery
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        try:
            # Our own hard cap (AI_TIMEOUT_SECONDS) around the whole call, including the retry.
            # Needed because Google rejects SDK deadlines under 10 s (see get_ai_client).
            response = await asyncio.wait_for(
                self._client.aio.models.generate_content(
                    model=self.model, contents=contents, config=config
                ),
                timeout=self._timeout_seconds,
            )
        except TimeoutError as exc:
            logger.warning("Gemini did not answer within %ss", self._timeout_seconds)
            raise AIUnavailableError() from exc
        except errors.APIError as exc:  # 4xx incl. 429 quota, 5xx incl. 503 overloaded
            logger.warning("Gemini API error %s: %s", exc.code, exc.message)
            raise AIUnavailableError() from exc
        except httpx.HTTPError as exc:  # timeouts and network failures
            logger.warning("Gemini request failed: %s", type(exc).__name__)
            raise AIUnavailableError() from exc

        text = (response.text or "").strip()
        if not text:
            # e.g. blocked by safety filters or cut off before producing any text
            reason = response.candidates[0].finish_reason if response.candidates else None
            logger.warning("Gemini returned no text (finish_reason=%s)", reason)
            raise AIUnavailableError()
        return text


@lru_cache
def get_ai_client() -> AIClient:
    """One shared client per process (FastAPI dependency; tests override it with a fake)."""
    settings = get_settings()
    client = genai.Client(
        api_key=settings.gemini_api_key,
        http_options=types.HttpOptions(
            # The SDK sends this to Google as a server deadline, and Google rejects anything
            # under 10 s. The user-facing limit (AI_TIMEOUT_SECONDS) is enforced in AIClient.
            timeout=max(GOOGLE_MIN_DEADLINE_MS, int(settings.ai_timeout_seconds * 1000)),
            # The SDK default is 5 attempts; one retry on server errors keeps the worst case
            # near 10 s. 429 (free-tier quota) is not retried: it won't clear in seconds.
            retry_options=types.HttpRetryOptions(
                attempts=2, http_status_codes=[500, 502, 503, 504]
            ),
        ),
    )
    return AIClient(client, settings.ai_model, settings.ai_timeout_seconds)
