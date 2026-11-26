"""Unit tests for the async LLM gateway."""

import httpx
import pytest

from flyright.llm.gateway import (
    CircuitBreaker,
    FakeLLM,
    LLMError,
    LLMGateway,
    LLMResult,
    LLMUnavailable,
    OpenAICompatProvider,
    Reply,
    cost_inr,
    estimate_tokens,
)

MESSAGES = [{"role": "user", "content": "Hello"}]


async def no_sleep(seconds: float) -> None:
    """Avoid real delays in retry tests."""


def make_gateway(providers, **kwargs):
    return LLMGateway(providers, sleep=no_sleep, **kwargs)


# 1
def test_cost_inr_calculation():
    result = cost_inr("gemini-3.8-flash", 1000, 500, 95.0)
    assert result == 0.249375


# 2
def test_estimate_tokens():
    assert estimate_tokens("abcdefgh") == 2
    assert estimate_tokens("") == 1


# 3
def test_provider_request_body():
    provider = OpenAICompatProvider(
        "test",
        "https://example.com/v1",
        "secret",
        "test-model",
    )
    body = provider._body(MESSAGES, 0.5, stream=True)

    assert body["model"] == "test-model"
    assert body["messages"] == MESSAGES
    assert body["temperature"] == 0.5
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}


# 4
async def test_provider_generate_success():
    def handler(request):
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer secret"
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "Hello back"}}],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                },
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatProvider(
        "test",
        "https://example.com/v1",
        "secret",
        "test-model",
        client=client,
    )

    reply = await provider.generate(MESSAGES)
    await client.aclose()

    assert reply == Reply("Hello back", 10, 5)


# 5
def test_provider_http_error_and_retry_after():
    response = httpx.Response(
        429,
        headers={"retry-after": "3"},
        text="Too many requests",
    )

    error = OpenAICompatProvider._error(response)

    assert error.retryable is True
    assert error.retry_after == 3.0
    assert "429" in str(error)


# 6
def test_provider_network_error_mapping():
    timeout = OpenAICompatProvider._network_error(httpx.ReadTimeout("timeout"))
    connection = OpenAICompatProvider._network_error(httpx.ConnectError("connection failed"))

    assert timeout.retryable is False
    assert connection.retryable is True


# 7
async def test_fake_provider_generate():
    provider = FakeLLM(
        "fake",
        "fake-model",
        ["A fake answer"],
    )

    reply = await provider.generate(MESSAGES)

    assert reply.text == "A fake answer"
    assert reply.tokens_in == 12
    assert reply.tokens_out == 3
    assert provider.calls == 1


# 8
def test_circuit_breaker_opens_and_half_opens():
    now = [0.0]
    breaker = CircuitBreaker(
        threshold=2,
        cooldown=10,
        clock=lambda: now[0],
    )

    assert breaker.state == "closed"
    assert breaker.allow()

    breaker.failure()
    assert breaker.state == "closed"

    breaker.failure()
    assert breaker.state == "open"
    assert not breaker.allow()

    now[0] = 11.0
    assert breaker.state == "half-open"
    assert breaker.allow()


# 9
def test_circuit_breaker_success_resets_failures():
    breaker = CircuitBreaker(threshold=2)

    breaker.failure()
    breaker.failure()

    assert breaker.state == "open"

    breaker.success()

    assert breaker.state == "closed"
    assert breaker.failures == 0


# 10
async def test_gateway_generate_success_and_recording():
    recorded = []

    async def recorder(row):
        recorded.append(row)

    provider = FakeLLM(
        "gemini",
        "gemini-3.8-flash",
        ["Hello!"],
    )
    gateway = make_gateway([provider], recorder=recorder)

    result = await gateway.generate(
        MESSAGES,
        prompt_version="test_v1",
    )

    assert isinstance(result, LLMResult)
    assert result.text == "Hello!"
    assert result.provider == "gemini"
    assert result.fallback_used is False
    assert len(recorded) == 1
    assert recorded[0]["status"] == "ok"
    assert recorded[0]["prompt_version"] == "test_v1"


# 11
async def test_gateway_retries_retryable_error():
    provider = FakeLLM(
        "gemini",
        "gemini-3.8-flash",
        [
            LLMError("temporary failure", retryable=True),
            "Recovered",
        ],
    )
    gateway = make_gateway([provider], max_attempts=2)

    result = await gateway.generate(MESSAGES)

    assert result.text == "Recovered"
    assert result.attempts == 2
    assert provider.calls == 2


# 12
async def test_gateway_does_not_retry_non_retryable_error():
    primary = FakeLLM(
        "gemini",
        "gemini-3.8-flash",
        [LLMError("unauthorized", retryable=False)],
    )
    backup = FakeLLM(
        "groq",
        "openai/gpt-oss-20b",
        ["Backup answer"],
    )
    gateway = make_gateway([primary, backup], max_attempts=3)

    result = await gateway.generate(MESSAGES)

    assert result.text == "Backup answer"
    assert primary.calls == 1
    assert backup.calls == 1
    assert result.fallback_used is True


# 13
async def test_gateway_falls_back_after_retry_exhaustion():
    primary = FakeLLM(
        "gemini",
        "gemini-3.8-flash",
        [
            LLMError("temporary", retryable=True),
            LLMError("still failing", retryable=True),
        ],
    )
    backup = FakeLLM(
        "groq",
        "openai/gpt-oss-20b",
        ["Backup answer"],
    )
    gateway = make_gateway(
        [primary, backup],
        max_attempts=2,
    )

    result = await gateway.generate(MESSAGES)

    assert result.text == "Backup answer"
    assert primary.calls == 2
    assert backup.calls == 1
    assert result.fallback_used is True


# 14
async def test_gateway_raises_when_all_providers_fail():
    primary = FakeLLM(
        "gemini",
        "gemini-3.8-flash",
        [LLMError("primary failed", retryable=False)],
    )
    backup = FakeLLM(
        "groq",
        "openai/gpt-oss-20b",
        [LLMError("backup failed", retryable=False)],
    )
    gateway = make_gateway([primary, backup])

    with pytest.raises(LLMUnavailable):
        await gateway.generate(MESSAGES)


# 15
async def test_gateway_skips_open_circuit():
    primary = FakeLLM(
        "gemini",
        "gemini-3.8-flash",
        [LLMError("failed", retryable=False)],
    )
    backup = FakeLLM(
        "groq",
        "openai/gpt-oss-20b",
        ["Backup answer"],
    )
    gateway = make_gateway(
        [primary, backup],
        breaker_threshold=1,
    )

    gateway.breakers["gemini"].failure()

    result = await gateway.generate(MESSAGES)

    assert result.text == "Backup answer"
    assert primary.calls == 0
    assert backup.calls == 1


# 16
async def test_gateway_without_providers_is_unavailable():
    gateway = make_gateway([])

    with pytest.raises(LLMUnavailable, match="no LLM provider"):
        await gateway.generate(MESSAGES)


# 17
async def test_gateway_stream_success():
    recorded = []

    async def recorder(row):
        recorded.append(row)

    provider = FakeLLM(
        "gemini",
        "gemini-3.8-flash",
        ["Hello from stream"],
    )
    gateway = make_gateway([provider], recorder=recorder)

    output = [item async for item in gateway.stream(MESSAGES)]

    pieces = [item for item in output if isinstance(item, str)]
    results = [item for item in output if isinstance(item, LLMResult)]

    assert "".join(pieces).strip() == "Hello from stream"
    assert len(results) == 1
    assert results[0].text.strip() == "Hello from stream"
    assert len(recorded) == 1


# 18
async def test_gateway_stream_falls_back_before_first_piece():
    primary = FakeLLM(
        "gemini",
        "gemini-3.8-flash",
        [LLMError("failed before output", retryable=True)],
    )
    backup = FakeLLM(
        "groq",
        "openai/gpt-oss-20b",
        ["Backup stream"],
    )
    gateway = make_gateway([primary, backup])

    output = [item async for item in gateway.stream(MESSAGES)]

    result = next(item for item in output if isinstance(item, LLMResult))

    assert result.text.strip() == "Backup stream"
    assert result.fallback_used is True
    assert primary.calls == 1
    assert backup.calls == 1


# 19
async def test_gateway_stream_does_not_fallback_mid_answer():
    primary = FakeLLM(
        "gemini",
        "gemini-3.8-flash",
        [
            (
                "partial answer",
                LLMError("stream interrupted", retryable=True),
            )
        ],
    )
    backup = FakeLLM(
        "groq",
        "openai/gpt-oss-20b",
        ["Backup must not be used"],
    )
    gateway = make_gateway([primary, backup])

    with pytest.raises(LLMUnavailable, match="failed mid-answer"):
        async for _ in gateway.stream(MESSAGES):
            pass

    assert primary.calls == 1
    assert backup.calls == 0


async def test_gateway_recovers_after_half_open_success():
    now = [0.0]

    primary = FakeLLM(
        "gemini",
        "gemini-3.8-flash",
        [
            LLMError("failure 1", retryable=False),
            LLMError("failure 2", retryable=False),
            LLMError("failure 3", retryable=False),
            "Recovered successfully",
        ],
    )

    gateway = LLMGateway(
        [primary],
        clock=lambda: now[0],
        breaker_threshold=3,
        breaker_cooldown=30,
        sleep=no_sleep,
    )

    for _ in range(3):
        with pytest.raises(LLMUnavailable):
            await gateway.generate(MESSAGES)

    breaker = gateway.breakers["gemini"]

    assert breaker.state == "open"
    assert primary.calls == 3

    now[0] = 31.0

    assert breaker.state == "half-open"

    result = await gateway.generate(MESSAGES)

    assert result.text == "Recovered successfully"
    assert primary.calls == 4
    assert breaker.state == "closed"
    assert breaker.failures == 0


# 21
async def test_provider_generate_supports_response_format():
    response_format = {"type": "json_object"}
    captured = {}

    def handler(request):
        captured.update(__import__("json").loads(request.content))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"label":"docs"}'}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            },
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    provider = OpenAICompatProvider(
        "test", "https://example.com/v1", "secret", "test-model", client=client
    )
    try:
        reply = await provider.generate(MESSAGES, response_format=response_format)
    finally:
        await client.aclose()

    assert captured["response_format"] == response_format
    assert reply.text == '{"label":"docs"}'
