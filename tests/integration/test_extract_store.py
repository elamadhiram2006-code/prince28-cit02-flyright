"""Integration tests for metadata extraction and PostgreSQL persistence."""

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from flyright.config import Settings
from flyright.db.models import Document, Page, ParseFailure
from flyright.db.session import make_engine, make_sessionmaker
from flyright.ingest.parse import ParsedDoc, ParsedPage
from flyright.ingest.store import save_document
from flyright.llm.extract import extract_metadata, extract_pending
from flyright.llm.gateway import LLMResult

RECORD = {
    "url": "https://example.org/fever.pdf",
    "source": "example",
    "licence": "CC BY 4.0",
    "title": "Fever Guidelines",
    "path": "data/raw/example/fever-test.pdf",
    "sha256": "cd" * 32,
}

PARSED = ParsedDoc(
    "pymupdf",
    "pdf",
    "Fever Guidelines",
    [
        ParsedPage(
            1,
            "# Fever Guidelines\n\nRest and fluids.",
            [],
        ),
    ],
)

VALID_RESPONSE = """{
    "doc_kind": "guideline",
    "year": 2024,
    "language": "en",
    "summary": "Guidance on fever management, hydration, and follow-up care.",
    "topics": ["fever", "hydration", "health"],
    "rule": ["Drink sufficient fluids"],
    "situation": [],
    "flight_duration": [],
    "compensation": [],
    "facilities": []
}"""


class FakeGateway:
    """Return a valid extraction response without calling an LLM provider."""

    def __init__(self, responses=None):
        self.responses = list(responses or [VALID_RESPONSE])
        self.calls = 0

    async def generate(self, messages, **kwargs):
        self.calls += 1
        response = self.responses.pop(0)
        return LLMResult(
            text=response,
            provider="fake",
            model="fake-model",
            tokens_in=100,
            tokens_out=50,
            latency_ms=1,
            attempts=1,
            fallback_used=False,
            cost_inr=0.0,
        )


@pytest_asyncio.fixture
async def session(database_url):
    """Provide a clean asynchronous PostgreSQL session."""
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
async def test_extract_metadata_persists_validated_metadata(session):
    await save_document(session, RECORD, PARSED)

    document = await session.scalar(select(Document).where(Document.sha256 == RECORD["sha256"]))
    assert document is not None

    gateway = FakeGateway()
    result = await extract_metadata(session, gateway, document.id)

    await session.refresh(document)

    assert result["status"] == "success"
    assert result["attempts"] == 1
    assert gateway.calls == 1

    assert document.metadata_["source"] == "example"
    assert document.metadata_["extract_status"] == "success"
    assert document.metadata_["doc_kind"] == "guideline"
    assert document.metadata_["extract"]["year"] == 2024
    assert document.metadata_["extract"]["topics"] == [
        "fever",
        "hydration",
        "health",
    ]


@pytest.mark.asyncio
async def test_extract_pending_skips_successful_document(session):
    await save_document(session, RECORD, PARSED)

    document = await session.scalar(select(Document).where(Document.sha256 == RECORD["sha256"]))
    assert document is not None

    gateway = FakeGateway()

    first = await extract_metadata(session, gateway, document.id)
    second = await extract_pending(
        session,
        gateway,
        limit=1,
        delay_seconds=0,
    )

    assert first["status"] == "success"
    assert second["total"] == 0
    assert second["skipped"] == 1
    assert gateway.calls == 1
