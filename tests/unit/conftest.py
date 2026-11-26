import re

import pytest
from fastapi.testclient import TestClient

from flyright.api.deps import get_gateway, get_repo, get_usage_repo
from flyright.api.main import create_app
from flyright.config import Settings
from flyright.llm.gateway import FakeLLM, LLMGateway

SAMPLE = [
    {"id": "001", "title": "Alpha guideline", "year": 2023},
    {"id": "002", "title": "Beta circular", "year": 2024},
    {"id": "003", "title": "Gamma notice", "year": 2025},
]


class FakeRepository:
    def __init__(self):
        self.records = SAMPLE

    async def list(self, q=None, limit=10, filters=None):
        records = self.records

        if q:
            records = [record for record in records if q.lower() in str(record).lower()]

        for key in filters or {}:
            if not re.fullmatch(r"[a-z_][a-z0-9_]{0,40}", key):
                raise ValueError(f"Invalid filter key: {key}")

        for key, value in (filters or {}).items():
            records = [record for record in records if str(record.get(key)) == value]

        return len(records), records[:limit]

    async def get(self, document_id):
        return next(
            (record for record in self.records if record["id"] == document_id),
            None,
        )


class FakeUsage:
    async def by_day(self, days=7):
        return [
            {
                "day": "2026-11-25",
                "calls": 3,
                "errors": 1,
                "fallbacks": 1,
                "tokens_in": 300,
                "tokens_out": 120,
                "cost_inr": 0.0642,
            }
        ]


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def client(tmp_path, llm):
    settings = Settings(
        app_env="ci",
        data_file=tmp_path / "records.json",
    )
    app = create_app(settings)

    app.dependency_overrides[get_repo] = FakeRepository
    app.dependency_overrides[get_gateway] = lambda: LLMGateway([llm])
    app.dependency_overrides[get_usage_repo] = lambda: FakeUsage()

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
