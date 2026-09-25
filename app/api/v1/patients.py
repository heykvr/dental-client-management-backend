from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import PatientServiceDep
from app.schemas.common import Page
from app.schemas.patient import PatientCreate, PatientResponse, PatientUpdate

router = APIRouter(prefix="/patients", tags=["patients"])


@router.get("", summary="List and search patients (newest first)")
async def list_patients(
    service: PatientServiceDep,
    search: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[PatientResponse]:
    return await service.list_patients(search, page, limit)


@router.post("", status_code=status.HTTP_201_CREATED, summary="Add a patient")
async def create_patient(data: PatientCreate, service: PatientServiceDep) -> PatientResponse:
    return await service.create_patient(data)


@router.get("/{patient_id}", summary="Get one patient by patient ID (e.g. PAT-0001)")
async def get_patient(patient_id: str, service: PatientServiceDep) -> PatientResponse:
    return await service.get_patient(patient_id)


@router.put("/{patient_id}", summary="Update a patient (send only the fields to change)")
async def update_patient(
    patient_id: str, data: PatientUpdate, service: PatientServiceDep
) -> PatientResponse:
    return await service.update_patient(patient_id, data)
