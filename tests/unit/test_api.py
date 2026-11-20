import pytest
from pydantic import ValidationError

from flyright.api.deps import get_db_session
from flyright.config import Settings


def test_health_is_ok(client):
    r = client.get("/health")

    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_health_returns_app_environment_and_version(client):
    r = client.get("/health")

    assert r.json()["app"] == "flyright"
    assert r.json()["env"] == "ci"
    assert r.json()["version"] == "dev"


def test_ready_when_database_is_available(client):
    class FakeSession:
        async def execute(self, query):
            return None

    async def override_session():
        yield FakeSession()

    client.app.dependency_overrides[get_db_session] = override_session

    r = client.get("/ready")

    assert r.status_code == 200
    assert r.json() == {
        "status": "ready",
        "checks": {"database": True},
    }


def test_ready_returns_503_when_database_fails(client):
    class FakeSession:
        async def execute(self, query):
            raise RuntimeError("Database unavailable")

    async def override_session():
        yield FakeSession()

    client.app.dependency_overrides[get_db_session] = override_session

    r = client.get("/ready")

    assert r.status_code == 503
    assert r.json() == {
        "status": "not_ready",
        "checks": {"database": False},
    }


def test_list_documents_paginates(client):
    r = client.get("/v1/documents", params={"limit": 2})
    body = r.json()
    assert r.status_code == 200
    assert body["total"] == 3
    assert len(body["items"]) == 2


def test_search_filters_records(client):
    r = client.get("/v1/documents", params={"q": "beta"})
    assert [d["id"] for d in r.json()["items"]] == ["002"]


def test_get_document_found(client):
    r = client.get("/v1/documents/001")
    assert r.status_code == 200
    assert r.json()["title"] == "Alpha guideline"


def test_missing_document_is_problem_details(client):
    r = client.get("/v1/documents/999")
    assert r.status_code == 404
    assert r.headers["content-type"] == "application/problem+json"
    body = r.json()
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["request_id"] == r.headers["X-Request-ID"]


def test_bad_limit_is_422_problem(client):
    r = client.get("/v1/documents", params={"limit": 0})
    assert r.status_code == 422
    assert r.json()["errors"][0]["field"] == "query.limit"


def test_request_id_is_echoed(client):
    r = client.get("/health", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"


def test_app_refuses_to_start_without_app_env(monkeypatch):
    monkeypatch.delenv("APP_ENV", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_metadata_filter_returns_matching_records(client):
    r = client.get("/v1/documents", params={"year": "2024"})

    assert r.status_code == 200
    assert [item["id"] for item in r.json()["items"]] == ["002"]


def test_invalid_metadata_filter_returns_400(client):
    r = client.get("/v1/documents", params={"bad-key": "value"})

    assert r.status_code == 400
    assert r.headers["content-type"] == "application/problem+json"


def test_app_refuses_to_start_without_database_url(monkeypatch):
    monkeypatch.setenv("APP_ENV", "ci")
    monkeypatch.delenv("DATABASE_URL", raising=False)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)
