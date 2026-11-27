from flyright.llm.classify import (
    accuracy,
    build_messages,
    classify,
    find_leaks,
    parse_label,
)
from flyright.llm.gateway import LLMResult


def test_build_messages_wraps_question():
    messages = build_messages("Classify the question.", "What are my rights?")

    assert messages[0] == {
        "role": "system",
        "content": "Classify the question.",
    }
    assert messages[1] == {
        "role": "user",
        "content": "<question>\nWhat are my rights?\n</question>",
    }


def test_parse_label_accepts_valid_labels():
    assert parse_label("docs") == "docs"
    assert parse_label("personal") == "personal"
    assert parse_label("off_topic") == "off_topic"


def test_parse_label_ignores_case_and_surrounding_whitespace():
    assert parse_label(" DOCS ") == "docs"
    assert parse_label(" Personal ") == "personal"


def test_parse_label_supports_off_topic_variants():
    assert parse_label("off topic") == "off_topic"
    assert parse_label("off-topic") == "off_topic"


def test_parse_label_rejects_extra_text():
    assert parse_label("The answer is docs") == "invalid"
    assert parse_label("docs.") == "invalid"
    assert parse_label("docs or personal") == "invalid"


def test_parse_label_rejects_unknown_labels():
    assert parse_label("unknown") == "invalid"
    assert parse_label("") == "invalid"


def test_parse_label_supports_custom_labels():
    assert parse_label("other", labels=("docs", "other")) == "other"
    assert parse_label("personal", labels=("docs", "other")) == "invalid"


async def test_classify_uses_gateway():
    class StubGateway:
        async def generate(
            self,
            messages,
            *,
            purpose="chat",
            prompt_version="",
            **options,
        ):
            assert purpose == "classify"
            assert prompt_version == "v1"
            assert options["temperature"] == 0
            assert messages[1]["content"] == ("<question>\nWhat are my rights?\n</question>")

            return LLMResult(
                text="docs",
                provider="test",
                model="test-model",
                tokens_in=10,
                tokens_out=1,
                latency_ms=10,
                attempts=1,
                fallback_used=False,
                cost_inr=0,
            )

    label, result = await classify(
        StubGateway(),
        "Classify the question.",
        "v1",
        "What are my rights?",
    )

    assert label == "docs"
    assert result.provider == "test"


async def test_classify_returns_invalid_for_non_exact_reply():
    class StubGateway:
        async def generate(self, messages, **options):
            return LLMResult(
                text="The answer is docs",
                provider="test",
                model="test-model",
                tokens_in=10,
                tokens_out=4,
                latency_ms=10,
                attempts=1,
                fallback_used=False,
                cost_inr=0,
            )

    label, _ = await classify(
        StubGateway(),
        "Classify the question.",
        "v1",
        "What are my rights?",
    )

    assert label == "invalid"


def test_accuracy_calculates_correct_predictions():
    records = [
        {"label": "docs", "got": "docs"},
        {"label": "personal", "got": "personal"},
        {"label": "off_topic", "got": "docs"},
    ]

    assert accuracy(records) == 2 / 3


def test_accuracy_handles_empty_records():
    assert accuracy([]) == 0


def test_find_leaks_detects_question_text():
    questions = [
        "What are my rights?",
        "Where is my baggage?",
    ]
    prompt = "Classify the question: What are my rights?"

    assert find_leaks(prompt, questions) == ["What are my rights?"]


def test_find_leaks_returns_empty_when_no_leak():
    questions = ["What are my rights?"]

    assert find_leaks("Classify the question.", questions) == []
