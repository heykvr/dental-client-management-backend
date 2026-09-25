from fastapi import APIRouter

from app.api.deps import CaseSheetServiceDep
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
    patient_id: str, data: CaseSheetInput, service: CaseSheetServiceDep
) -> CaseSheetResponse:
    return await service.save_case_sheet(patient_id, data)
