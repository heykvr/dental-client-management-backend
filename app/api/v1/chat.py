from fastapi import APIRouter

from app.api.deps import ChatServiceDep
from app.core.rate_limit import ai_rate_limit
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/patients/{patient_id}/chat", tags=["chat"])


@router.post(
    "",
    dependencies=[ai_rate_limit],
    summary="Ask about this patient; answers come only from the patient's record (stateless)",
)
async def chat(patient_id: str, data: ChatRequest, service: ChatServiceDep) -> ChatResponse:
    return await service.reply(patient_id, data)
