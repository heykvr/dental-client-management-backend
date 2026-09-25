import asyncio

from app.repositories.counter_repo import CounterRepository


async def test_ids_are_sequential_and_zero_padded(db):
    repo = CounterRepository(db)
    await repo.ensure_patient_counter()

    assert [await repo.next_patient_id() for _ in range(3)] == ["PAT-0001", "PAT-0002", "PAT-0003"]


async def test_ensure_counter_never_resets_existing_sequence(db):
    repo = CounterRepository(db)
    await repo.ensure_patient_counter()
    await repo.next_patient_id()

    await repo.ensure_patient_counter()

    assert await repo.next_patient_id() == "PAT-0002"


async def test_concurrent_requests_get_unique_ids(db):
    repo = CounterRepository(db)
    await repo.ensure_patient_counter()

    ids = await asyncio.gather(*(repo.next_patient_id() for _ in range(20)))

    assert sorted(ids) == [f"PAT-{n:04d}" for n in range(1, 21)]
