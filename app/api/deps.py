from typing import Annotated

from fastapi import Depends

from app.core.database import DbDep
from app.repositories.counter_repo import CounterRepository
from app.repositories.patient_repo import PatientRepository
from app.services.patient_service import PatientService


def get_patient_service(db: DbDep) -> PatientService:
    return PatientService(PatientRepository(db), CounterRepository(db))


PatientServiceDep = Annotated[PatientService, Depends(get_patient_service)]
