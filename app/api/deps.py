from typing import Annotated

from fastapi import Depends

from app.core.database import DbDep
from app.repositories.case_sheet_repo import CaseSheetRepository
from app.repositories.counter_repo import CounterRepository
from app.repositories.patient_repo import PatientRepository
from app.services.case_sheet_service import CaseSheetService
from app.services.dashboard_service import DashboardService
from app.services.patient_service import PatientService


def get_patient_service(db: DbDep) -> PatientService:
    return PatientService(PatientRepository(db), CounterRepository(db))


def get_case_sheet_service(db: DbDep) -> CaseSheetService:
    return CaseSheetService(CaseSheetRepository(db))


def get_dashboard_service(db: DbDep) -> DashboardService:
    return DashboardService(PatientRepository(db), CaseSheetRepository(db))


PatientServiceDep = Annotated[PatientService, Depends(get_patient_service)]
CaseSheetServiceDep = Annotated[CaseSheetService, Depends(get_case_sheet_service)]
DashboardServiceDep = Annotated[DashboardService, Depends(get_dashboard_service)]
