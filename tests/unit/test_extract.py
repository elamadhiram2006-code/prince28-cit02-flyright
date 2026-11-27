import json

from flyright.llm.doc_meta import DocMeta
from flyright.llm.extract import extract_metadata
from flyright.llm.gateway import LLMResult, LLMUnavailable

VALID_METADATA = {
    "doc_kind": "guideline",
    "year": 2024,
    "language": "en",
    "summary": "This document explains passenger rights and airline responsibilities.",
    "topics": ["passenger rights", "airline"],
    "rule": ["Airlines must provide required assistance."],
    "situation": [],
    "flight_duration": [],
    "compensation": [],
    "facilities": [],
}


class FakePage:
    page_no = 1
    text = "This is a sample aviation passenger rights document."


class FakeDocument:
    id = 1
    metadata_ = {"source": "test", "pages": 1}


class FakeScalars:
    def all(self):
        return [FakePage()]


class FakeResult:
    def scalars(self):
        return FakeScalars()


class FakeSession:
    def __init__(self, pages=True):
        self.document = FakeDocument()
        self.pages = pages
        self.commits = 0

    async def get(self, model, document_id):
        return self.document if document_id == 1 else None

    async def execute(self, statement):
        return FakeResult() if self.pages else EmptyResult()

    async def commit(self):
        self.commits += 1


class EmptyScalars:
    def all(self):
        return []


class EmptyResult:
    def scalars(self):
        return EmptyScalars()


class FakeGateway:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = 0

    async def generate(self, messages, **options):
        self.calls += 1
        assert options["purpose"] == "extract"
        assert options["temperature"] == 0
        reply = self.replies.pop(0)

        if isinstance(reply, Exception):
            raise reply

        return LLMResult(
            text=reply,
            provider="test",
            model="test-model",
            tokens_in=10,
            tokens_out=10,
            latency_ms=10,
            attempts=1,
            fallback_used=False,
            cost_inr=0,
        )


def test_doc_meta_accepts_valid_metadata():
    metadata = DocMeta.model_validate(VALID_METADATA)

    assert metadata.doc_kind == "guideline"
    assert metadata.year == 2024
    assert metadata.language == "en"
    assert "passenger rights" in metadata.topics


def test_doc_meta_rejects_unknown_fields():
    invalid = {**VALID_METADATA, "unknown_field": "not allowed"}

    try:
        DocMeta.model_validate(invalid)
    except ValueError:
        pass
    else:
        raise AssertionError("Unknown fields should be rejected")


async def test_extract_metadata_saves_valid_result():
    session = FakeSession()
    gateway = FakeGateway([json.dumps(VALID_METADATA)])

    result = await extract_metadata(session, gateway, 1)

    assert result["status"] == "success"
    assert result["attempts"] == 1
    assert session.document.metadata_["extract_status"] == "success"
    assert session.document.metadata_["extract"]["doc_kind"] == "guideline"
    assert session.document.metadata_["source"] == "test"
    assert session.commits == 2


async def test_extract_metadata_repairs_invalid_json():
    session = FakeSession()
    gateway = FakeGateway(
        [
            "not valid JSON",
            json.dumps(VALID_METADATA),
        ]
    )

    result = await extract_metadata(session, gateway, 1)

    assert result["status"] == "success"
    assert result["attempts"] == 2
    assert gateway.calls == 2
    assert session.document.metadata_["extract_status"] == "success"


async def test_extract_metadata_returns_failed_after_invalid_replies():
    session = FakeSession()
    gateway = FakeGateway(
        [
            "invalid JSON",
            "still invalid",
            "also invalid",
        ]
    )

    result = await extract_metadata(session, gateway, 1)

    assert result["status"] == "failed"
    assert result["attempts"] == 3
    assert gateway.calls == 3
    assert session.document.metadata_["extract_status"] == "failed"
    assert "extract_error" in session.document.metadata_


async def test_extract_metadata_skips_document_without_pages():
    session = FakeSession(pages=False)
    gateway = FakeGateway([])

    result = await extract_metadata(session, gateway, 1)

    assert result["status"] == "skipped"
    assert gateway.calls == 0
    assert session.commits == 0


async def test_extract_metadata_handles_unavailable_gateway():
    session = FakeSession()
    gateway = FakeGateway([LLMUnavailable("Providers unavailable")])

    result = await extract_metadata(session, gateway, 1)

    assert result["status"] == "failed"
    assert result["attempts"] == 1
    assert session.document.metadata_["extract_status"] == "failed"
