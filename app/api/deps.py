from typing import Annotated

from fastapi import Depends

from app.core.database import DbDep
from app.repositories.case_sheet_repo import CaseSheetRepository
from app.repositories.counter_repo import CounterRepository
from app.repositories.patient_repo import PatientRepository
from app.services.ai_service import AIClient, get_ai_client
from app.services.case_sheet_service import CaseSheetService
from app.services.chat_service import ChatService
from app.services.dashboard_service import DashboardService
from app.services.patient_service import PatientService
from app.services.summary_service import SummaryService


def get_patient_service(db: DbDep) -> PatientService:
    return PatientService(PatientRepository(db), CounterRepository(db))


def get_case_sheet_service(db: DbDep) -> CaseSheetService:
    return CaseSheetService(CaseSheetRepository(db))


def get_dashboard_service(db: DbDep) -> DashboardService:
    return DashboardService(PatientRepository(db), CaseSheetRepository(db))


def get_summary_service(
    db: DbDep, ai: Annotated[AIClient, Depends(get_ai_client)]
) -> SummaryService:
    return SummaryService(CaseSheetRepository(db), ai)


def get_chat_service(db: DbDep, ai: Annotated[AIClient, Depends(get_ai_client)]) -> ChatService:
    return ChatService(CaseSheetRepository(db), ai)


PatientServiceDep = Annotated[PatientService, Depends(get_patient_service)]
CaseSheetServiceDep = Annotated[CaseSheetService, Depends(get_case_sheet_service)]
DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
SummaryServiceDep = Annotated[SummaryService, Depends(get_summary_service)]
ChatServiceDep = Annotated[ChatService, Depends(get_chat_service)]
