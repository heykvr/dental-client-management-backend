from fastapi import APIRouter, BackgroundTasks, Request

from app.api.deps import SummaryServiceDep
from app.core.rate_limit import ai_rate_limit, try_consume_ai_quota
from app.schemas.case_sheet import CaseSheetResponse
from app.services.summary_service import SummaryService

router = APIRouter(prefix="/patients/{patient_id}/summary", tags=["ai summary"])


@router.post(
    "",
    dependencies=[ai_rate_limit],
    summary="Generate the AI summary now (Regenerate / Retry); waits for the result",
)
async def generate_summary(patient_id: str, service: SummaryServiceDep) -> CaseSheetResponse:
    return await service.generate(patient_id)


async def queue_summary_refresh(
    patient_id: str,
    request: Request,
    background_tasks: BackgroundTasks,
    service: SummaryService,
) -> bool:
    """After a save: if the summarised content changed, start a background regeneration.

    Returns True if one was queued. Skipped (summary just shows as outdated) when nothing
    relevant changed, a run for this content is already going, or the client's AI quota is
    used up, so fast repeated saves can't burn the free-tier quota (see DECISIONS.md).
    """
    requested_hash = await service.pending_refresh(patient_id)
    if requested_hash is None or not try_consume_ai_quota(request):
        return False
    await service.mark_generating(patient_id, requested_hash)
    background_tasks.add_task(service.generate_in_background, patient_id)
    return True
