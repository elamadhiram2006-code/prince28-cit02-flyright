"""Integration tests for parsing and storing documents in PostgreSQL."""

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from flyright.config import Settings
from flyright.db.models import Document, Page, ParseFailure
from flyright.db.session import make_engine, make_sessionmaker
from flyright.ingest.parse import (
    ParsedDoc,
    ParsedPage,
    ParseError,
)
from flyright.ingest.store import (
    document_id,
    parsed_ids,
    save_document,
    save_failure,
)

RECORD = {
    "url": "https://example.org/fever.pdf",
    "source": "example",
    "licence": "CC BY 4.0",
    "title": "",
    "path": "data/raw/example/fever-1a2b3c4d.pdf",
    "sha256": "ab" * 32,
}

PARSED = ParsedDoc(
    "pymupdf",
    "pdf",
    "Fever Guidelines",
    [
        ParsedPage(
            1,
            "# Fever Guidelines\n\n## Dengue\n\nRest and fluids.",
            [],
        ),
        ParsedPage(
            2,
            "Review after two days.",
            ["Fever Guidelines", "Dengue"],
        ),
    ],
)


@pytest_asyncio.fixture
async def session(database_url):
    """Provide a clean asynchronous database session for each test."""
    settings = Settings(
        app_env="ci",
        database_url=database_url,
        _env_file=None,
    )
    engine = make_engine(settings)
    session_factory = make_sessionmaker(engine)

    try:
        async with session_factory() as db:
            await db.execute(delete(Page))
            await db.execute(delete(Document))
            await db.execute(delete(ParseFailure))
            await db.commit()

            yield db
    finally:
        await engine.dispose()


@pytest.mark.asyncio
async def test_save_document(session):
    """Save a parsed document and verify its pages and metadata."""
    await save_document(session, RECORD, PARSED)

    document = await session.scalar(
        select(Document).where(Document.external_id == document_id(RECORD["sha256"]))
    )

    assert document is not None
    assert document.title == "Fever Guidelines"
    assert document.doc_type == "pdf"
    assert document.metadata_["pages"] == 2

    pages = list(
        await session.scalars(
            select(Page).where(Page.document_id == document.id).order_by(Page.page_no)
        )
    )

    assert len(pages) == 2
    assert pages[0].page_no == 1
    assert pages[1].page_no == 2
    assert pages[1].headings == ["Fever Guidelines", "Dengue"]

    assert await parsed_ids(session) == {document_id(RECORD["sha256"])}


@pytest.mark.asyncio
async def test_save_failure_increments_attempts(session):
    """Repeated failures for the same file increment the attempt count."""
    error = ParseError(
        "corrupt_pdf",
        "Unable to read PDF contents.",
    )

    await save_failure(session, RECORD, error)
    await save_failure(session, RECORD, error)

    failure = await session.scalar(select(ParseFailure).where(ParseFailure.path == RECORD["path"]))

    assert failure is not None
    assert failure.attempts == 2
    assert failure.reason == "corrupt_pdf"


@pytest.mark.asyncio
async def test_save_document_clears_previous_failure(session):
    """Successfully parsing a file removes its previous failure record."""
    error = ParseError(
        "corrupt_pdf",
        "Unable to read PDF contents.",
    )

    await save_failure(session, RECORD, error)

    await save_document(session, RECORD, PARSED)

    failures = list(await session.scalars(select(ParseFailure)))
    pages = list(await session.scalars(select(Page)))

    assert failures == []
    assert len(pages) == 2
