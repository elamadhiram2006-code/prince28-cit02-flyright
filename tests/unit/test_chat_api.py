"""Tests for /v1/chat and /v1/usage."""

import json

from flyright.llm.gateway import LLMError


def events(body: str) -> list[tuple[str, dict]]:
    """Parse server-sent events from a response body."""
    output = []

    for block in body.strip().split("\n\n"):
        name = ""

        for line in block.splitlines():
            if line.startswith("event:"):
                name = line[6:].strip()
            elif line.startswith("data:"):
                output.append((name, json.loads(line[5:])))

    return output


def test_chat_without_streaming_returns_json(client, llm):
    llm.script = ["Use curly braces in the path."]

    response = client.post(
        "/v1/chat",
        json={
            "message": "How do I declare a path parameter?",
            "stream": False,
        },
    )

    assert response.status_code == 200

    body = response.json()
    assert body["answer"] == "Use curly braces in the path."
    assert body["provider"] == "fake"
    assert body["tokens_out"] == 6
    assert "cost_inr" in body


def test_chat_streams_pieces_and_ends_with_done_event(client, llm):
    llm.script = ["Use curly braces in the path."]

    response = client.post(
        "/v1/chat",
        json={"message": "How do I declare a path parameter?"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    received = events(response.text)
    answer = "".join(data["delta"] for name, data in received if name == "")

    assert answer.strip() == "Use curly braces in the path."
    assert received[-1][0] == "done"
    assert received[-1][1]["model"] == "fake-1"


def test_the_system_prompt_is_loaded_from_the_prompt_file(client):
    assert "not sure" in client.app.state.system_prompt.lower()


def test_an_empty_message_is_a_422_problem(client):
    response = client.post(
        "/v1/chat",
        json={"message": ""},
    )

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"


def test_when_no_model_can_answer_the_api_returns_503(client, llm):
    llm.script = [LLMError("HTTP 401: invalid API key", retryable=False)]

    response = client.post(
        "/v1/chat",
        json={"message": "hello"},
    )

    assert response.status_code == 503
    assert "No model could answer" in response.json()["detail"]


def test_a_mid_stream_failure_is_reported_as_an_error_event(client, llm):
    llm.script = [("partial", LLMError("HTTP 503: overloaded", retryable=True))]

    response = client.post(
        "/v1/chat",
        json={"message": "hello"},
    )

    assert response.status_code == 200
    assert events(response.text)[-1][0] == "error"


def test_usage_reports_tokens_and_rupees_per_day(client):
    response = client.get("/v1/usage")

    assert response.status_code == 200

    body = response.json()
    assert body["days"][0]["tokens_in"] == 300
    assert body["total_cost_inr"] == 0.0642
    assert body["calls"] == 3
