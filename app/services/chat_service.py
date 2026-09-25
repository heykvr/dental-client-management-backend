from google.genai import types

from app.repositories.case_sheet_repo import CaseSheetRepository
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.ai_service import AIClient, format_patient_record, load_prompt
from app.services.case_sheet_service import load_patient_with_case_sheet
from app.services.patient_service import normalize_patient_id

CHAT_MAX_OUTPUT_TOKENS = 300

# Gemini calls the assistant role "model"
GEMINI_ROLES = {"user": "user", "assistant": "model"}


def build_chat_prompt(doc: dict, request: ChatRequest) -> tuple[str, list[types.Content]]:
    """System prompt (rules + the patient's record) and the conversation for Gemini.
    Shared by the API and the eval runner, so evals test exactly what users get."""
    # str.replace, not str.format: record text may contain braces
    system = load_prompt("chat_system").replace("{record}", format_patient_record(doc))
    turns = [*request.recent_history(), None]  # None = the new message
    contents = [
        types.Content(
            role=GEMINI_ROLES[turn.role] if turn else "user",
            parts=[types.Part(text=turn.content if turn else request.message)],
        )
        for turn in turns
    ]
    return system, contents


class ChatService:
    """Stateless, grounded chat: the patient's record is rebuilt from the database for every
    question, and nothing from the conversation is stored."""

    def __init__(self, case_sheets: CaseSheetRepository, ai: AIClient):
        self._case_sheets = case_sheets
        self._ai = ai

    async def reply(self, patient_id: str, request: ChatRequest) -> ChatResponse:
        doc = await load_patient_with_case_sheet(
            self._case_sheets, normalize_patient_id(patient_id)
        )
        system, contents = build_chat_prompt(doc, request)
        text = await self._ai.generate(
            system=system, contents=contents, max_output_tokens=CHAT_MAX_OUTPUT_TOKENS
        )
        return ChatResponse(reply=text)
