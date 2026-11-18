import re

import pytest
from fastapi.testclient import TestClient

from flyright.api.deps import get_repo
from flyright.api.main import create_app
from flyright.config import Settings

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

        # Validate metadata filter keys.
        for key in filters or {}:
            if not re.fullmatch(r"[a-z_][a-z0-9_]{0,40}", key):
                raise ValueError(f"Invalid filter key: {key}")

        # Apply metadata filters.
        for key, value in (filters or {}).items():
            records = [record for record in records if str(record.get(key)) == value]

        return len(records), records[:limit]

    async def get(self, document_id):
        return next(
            (record for record in self.records if record["id"] == document_id),
            None,
        )


@pytest.fixture
def client(tmp_path):
    settings = Settings(
        app_env="ci",
        data_file=tmp_path / "records.json",
    )
    app = create_app(settings)
    app.dependency_overrides[get_repo] = FakeRepository

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
