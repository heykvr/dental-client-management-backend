from app.core.exceptions import PatientNotFoundError
from app.repositories.case_sheet_repo import CaseSheetRepository
from app.repositories.counter_repo import CounterRepository
from app.repositories.patient_repo import PatientRepository
from app.schemas.common import Page
from app.schemas.patient import PatientCreate, PatientResponse, PatientUpdate


def normalize_patient_id(patient_id: str) -> str:
    # Accept "pat-0001" or " PAT-0001 " from URLs
    return patient_id.strip().upper()


class PatientService:
    def __init__(
        self,
        patients: PatientRepository,
        counters: CounterRepository,
        case_sheets: CaseSheetRepository,
    ):
        self._patients = patients
        self._counters = counters
        self._case_sheets = case_sheets

    async def create_patient(self, data: PatientCreate) -> PatientResponse:
        patient_id = await self._counters.next_patient_id()
        doc = await self._patients.create(patient_id, data.model_dump())
        # Every patient starts with an empty, not_started case sheet (1:1)
        await self._case_sheets.create_empty(patient_id)
        return PatientResponse.model_validate(doc)

    async def get_patient(self, patient_id: str) -> PatientResponse:
        doc = await self._patients.get(normalize_patient_id(patient_id))
        if doc is None:
            raise PatientNotFoundError()
        return PatientResponse.model_validate(doc)

    async def list_patients(
        self, search: str | None, page: int, limit: int
    ) -> Page[PatientResponse]:
        docs, total = await self._patients.list(search, skip=(page - 1) * limit, limit=limit)
        return Page[PatientResponse](
            items=[PatientResponse.model_validate(doc) for doc in docs],
            total=total,
            page=page,
            limit=limit,
        )

    async def update_patient(self, patient_id: str, data: PatientUpdate) -> PatientResponse:
        # exclude_unset: only fields the client actually sent are changed
        changes = data.model_dump(exclude_unset=True)
        doc = await self._patients.update(normalize_patient_id(patient_id), changes)
        if doc is None:
            raise PatientNotFoundError()
        return PatientResponse.model_validate(doc)
