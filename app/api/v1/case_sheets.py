from fastapi import APIRouter, BackgroundTasks, Request

from app.api.deps import CaseSheetServiceDep, SummaryServiceDep
from app.api.v1.summaries import queue_summary_refresh
from app.schemas.case_sheet import CaseSheetInput, CaseSheetResponse

router = APIRouter(prefix="/patients/{patient_id}/case-sheet", tags=["case sheets"])


@router.get("", summary="Get a patient's case sheet (empty and not_started until data is saved)")
async def get_case_sheet(patient_id: str, service: CaseSheetServiceDep) -> CaseSheetResponse:
    return await service.get_case_sheet(patient_id)


@router.put(
    "",
    summary="Save case sheet sections (partial allowed); status is recalculated by the server",
)
async def save_case_sheet(
    patient_id: str,
    data: CaseSheetInput,
    request: Request,
    background_tasks: BackgroundTasks,
    service: CaseSheetServiceDep,
    summaries: SummaryServiceDep,
) -> CaseSheetResponse:
    sheet = await service.save_case_sheet(patient_id, data)
    # The save returns instantly; the summary refreshes in the background if content changed
    if await queue_summary_refresh(patient_id, request, background_tasks, summaries):
        sheet.ai_summary.state = "generating"
    return sheet
