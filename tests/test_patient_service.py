import pytest

from app.core.exceptions import PatientNotFoundError
from app.repositories.counter_repo import CounterRepository
from app.repositories.patient_repo import PatientRepository
from app.schemas.patient import PatientCreate, PatientUpdate
from app.services.patient_service import PatientService

NEW_PATIENT = PatientCreate(
    first_name="Aarav",
    last_name="Ramesh",
    date_of_birth="2002-05-14",
    gender="male",
    phone="+91 98765 43210",
    address="12 MG Road, Bengaluru",
)


@pytest.fixture
async def service(db):
    patients = PatientRepository(db)
    counters = CounterRepository(db)
    await patients.ensure_indexes()
    await counters.ensure_patient_counter()
    return PatientService(patients, counters)


async def test_create_assigns_sequential_ids(service):
    first = await service.create_patient(NEW_PATIENT)
    second = await service.create_patient(NEW_PATIENT)

    assert (first.patient_id, second.patient_id) == ("PAT-0001", "PAT-0002")
    assert first.full_name == "Aarav Ramesh"
    assert first.phone == "+919876543210"


async def test_get_accepts_lowercase_id(service):
    await service.create_patient(NEW_PATIENT)

    patient = await service.get_patient(" pat-0001 ")

    assert patient.patient_id == "PAT-0001"


async def test_get_missing_patient_raises_not_found(service):
    with pytest.raises(PatientNotFoundError):
        await service.get_patient("PAT-9999")


async def test_list_returns_page_metadata(service):
    for _ in range(3):
        await service.create_patient(NEW_PATIENT)

    page = await service.list_patients(search=None, page=2, limit=2)

    assert page.total == 3
    assert (page.page, page.limit) == (2, 2)
    assert [p.patient_id for p in page.items] == ["PAT-0001"]


async def test_update_changes_only_sent_fields(service):
    await service.create_patient(NEW_PATIENT)

    updated = await service.update_patient("PAT-0001", PatientUpdate(address="45 Park Street"))

    assert updated.address == "45 Park Street"
    assert updated.first_name == "Aarav"
    assert updated.last_name == "Ramesh"


async def test_update_missing_patient_raises_not_found(service):
    with pytest.raises(PatientNotFoundError):
        await service.update_patient("PAT-9999", PatientUpdate(address="45 Park Street"))
