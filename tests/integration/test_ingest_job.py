"""Integration tests for ingestion jobs and worker state transitions."""

import pytest
from arq import Retry
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from flyright.config import Settings
from flyright.db.ingest_jobs import IngestRepository
from flyright.db.models import IngestItem
from flyright.workers.ingest import Permanent, ingest_document


@pytest.fixture
async def ingest_db(database_url):
    engine = create_async_engine(database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield session_factory
    finally:
        await engine.dispose()


async def create_item(session_factory, record=None):
    async with session_factory() as session:
        repository = IngestRepository(session)
        job_id = await repository.create([record or {"url": "https://example.com/test.pdf"}])
        item_id = await session.scalar(select(IngestItem.id).where(IngestItem.job_id == job_id))
        return job_id, item_id


async def read_item(session_factory, item_id):
    async with session_factory() as session:
        return await session.get(IngestItem, item_id)


def worker_context(session_factory):
    return {
        "settings": Settings(
            app_env="ci",
            database_url="postgresql+asyncpg://localhost/test",
            ingest_max_tries=3,
            _env_file=None,
        ),
        "sessionmaker": session_factory,
    }


@pytest.mark.asyncio
async def test_successful_ingestion_is_idempotent(ingest_db, monkeypatch):
    _, item_id = await create_item(ingest_db)
    calls = []

    async def successful_process(ctx, session, item):
        calls.append(item.id)
        return "done", 2

    monkeypatch.setattr("flyright.workers.ingest.process", successful_process)
    ctx = worker_context(ingest_db)

    assert await ingest_document(ctx, item_id) == "done"
    assert await ingest_document(ctx, item_id) == "ignored"

    item = await read_item(ingest_db, item_id)
    assert item.status == "done"
    assert item.attempts == 1
    assert item.pages == 2
    assert calls == [item_id]


@pytest.mark.asyncio
async def test_permanent_failure_is_not_retried(ingest_db, monkeypatch):
    _, item_id = await create_item(ingest_db)

    async def permanent_process(ctx, session, item):
        raise Permanent("Unsupported document format")

    monkeypatch.setattr("flyright.workers.ingest.process", permanent_process)

    result = await ingest_document(worker_context(ingest_db), item_id)
    item = await read_item(ingest_db, item_id)

    assert result == "failed"
    assert item.status == "failed"
    assert item.attempts == 1
    assert item.error == "Unsupported document format"


@pytest.mark.asyncio
async def test_temporary_failure_is_retried(ingest_db, monkeypatch):
    _, item_id = await create_item(ingest_db)

    async def temporary_process(ctx, session, item):
        raise RuntimeError("Temporary network failure")

    monkeypatch.setattr("flyright.workers.ingest.process", temporary_process)

    with pytest.raises(Retry):
        await ingest_document(worker_context(ingest_db), item_id)

    item = await read_item(ingest_db, item_id)
    assert item.status == "queued"
    assert item.attempts == 1
    assert item.error == "Temporary network failure"


@pytest.mark.asyncio
async def test_worker_recovery_finds_abandoned_items(ingest_db):
    async with ingest_db() as session:
        repository = IngestRepository(session)
        job_id = await repository.create(
            [
                {"url": "https://example.com/first.pdf"},
                {"url": "https://example.com/second.pdf"},
            ]
        )
        item_ids = list(
            await session.scalars(
                select(IngestItem.id).where(IngestItem.job_id == job_id).order_by(IngestItem.id)
            )
        )

    first_id, second_id = item_ids

    async with ingest_db() as session:
        second = await session.get(IngestItem, second_id)
        second.status = "running"
        second.attempts = 1
        await session.commit()

    async with ingest_db() as session:
        repository = IngestRepository(session)
        recovered_ids = await repository.open_item_ids(job_id)

    assert set(recovered_ids) == {first_id, second_id}
