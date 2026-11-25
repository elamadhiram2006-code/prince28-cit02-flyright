"""Tests for the LLM gateway and provider fallback."""

from unittest.mock import Mock, patch

import httpx
import pytest

from flyright.config import Settings
from flyright.llm.gateway import LLMError, LLMGateway


@pytest.fixture
def settings() -> Settings:
    return Settings(
        app_env="local",
        database_url="postgresql://localhost:5432/flyright",
        gemini_api_key="dummy",  # pragma: allowlist secret
        groq_api_key="dummy",  # pragma: allowlist secret
    )


@pytest.fixture
def messages() -> list[dict[str, str]]:
    return [{"role": "user", "content": "Hello"}]


def make_response(content: str) -> Mock:
    response = Mock()
    response.status_code = 200
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    response.raise_for_status.return_value = None
    return response


def test_primary_provider_success(
    settings: Settings,
    messages: list[dict[str, str]],
) -> None:
    gateway = LLMGateway(settings)

    with patch(
        "flyright.llm.gateway.httpx.post",
        return_value=make_response("Hello from Gemini"),
    ) as post:
        result = gateway.chat(messages)

    assert result == "Hello from Gemini"
    assert post.call_count == 1
    assert "generativelanguage.googleapis.com" in post.call_args.args[0]


def test_fallback_to_groq_when_gemini_fails(
    settings: Settings,
    messages: list[dict[str, str]],
) -> None:
    gateway = LLMGateway(settings)

    with patch(
        "flyright.llm.gateway.httpx.post",
        side_effect=[
            httpx.HTTPStatusError(
                "Gemini unavailable",
                request=Mock(),
                response=Mock(),
            ),
            make_response("Hello from Groq"),
        ],
    ) as post:
        result = gateway.chat(messages)

    assert result == "Hello from Groq"
    assert post.call_count == 2
    assert "generativelanguage.googleapis.com" in post.call_args_list[0].args[0]
    assert "api.groq.com" in post.call_args_list[1].args[0]


def test_missing_gemini_key_uses_groq(
    settings: Settings,
    messages: list[dict[str, str]],
) -> None:
    settings.gemini_api_key = ""
    gateway = LLMGateway(settings)

    with patch(
        "flyright.llm.gateway.httpx.post",
        return_value=make_response("Hello from Groq"),
    ) as post:
        result = gateway.chat(messages)

    assert result == "Hello from Groq"
    assert post.call_count == 1
    assert "api.groq.com" in post.call_args.args[0]


def test_all_providers_fail(
    settings: Settings,
    messages: list[dict[str, str]],
) -> None:
    gateway = LLMGateway(settings)

    with (
        patch(
            "flyright.llm.gateway.httpx.post",
            side_effect=httpx.ConnectError("Connection failed"),
        ),
        pytest.raises(LLMError, match="All LLM providers failed"),
    ):
        gateway.chat(messages)


def test_empty_provider_response_uses_fallback(
    settings: Settings,
    messages: list[dict[str, str]],
) -> None:
    gateway = LLMGateway(settings)

    with patch(
        "flyright.llm.gateway.httpx.post",
        side_effect=[
            make_response(""),
            make_response("Groq response"),
        ],
    ):
        result = gateway.chat(messages)

    assert result == "Groq response"
