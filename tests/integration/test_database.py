"""Integration tests against a temporary PostgreSQL database."""

import asyncio
import json
import os
import subprocess
import sys

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from flyright.api.main import create_app
from flyright.config import Settings
from flyright.db.repository import DocumentRepository


@pytest.fixture(scope="module")
def seeded_database(database_url):
    """Insert one known document into the migrated test database."""
    engine = create_async_engine(database_url)

    async def seed():
        async with engine.begin() as conn:
            await conn.execute(
                text("""
                    INSERT INTO documents
                    (external_id, title, sha256, metadata)
                    VALUES (
                        'integration-001',
                        'Integration Test Document',
                        :sha,
                        CAST(:metadata AS jsonb)
                    )
                    ON CONFLICT (external_id) DO NOTHING
                """),
                {
                    "sha": "a" * 64,
                    "metadata": json.dumps(
                        {
                            "situation": "integration test situation",
                            "notice_period": "24 hours",
                            "flight_duration": "2 hours",
                            "compensation": "test compensation",
                        }
                    ),
                },
            )

    try:
        asyncio.run(seed())
    finally:
        asyncio.run(engine.dispose())

    return database_url


@pytest.fixture(scope="module")
def db_client(seeded_database):
    settings = Settings(
        app_env="ci",
        database_url=seeded_database,
        _env_file=None,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def test_migrations_create_tables(database_url):
    engine = create_async_engine(database_url)

    async def check():
        async with engine.connect() as conn:
            result = await conn.exec_driver_sql(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"
            )
            tables = {row[0] for row in result}
        assert {"documents", "pages", "alembic_version"} <= tables

    try:
        asyncio.run(check())
    finally:
        asyncio.run(engine.dispose())


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("filters", "expected"),
    [
        ({"situation": "integration test situation"}, ["integration-001"]),
        ({"notice_period": "24 hours"}, ["integration-001"]),
        ({"flight_duration": "2 hours"}, ["integration-001"]),
        ({"compensation": "test compensation"}, ["integration-001"]),
    ],
)
async def test_jsonb_filters(seeded_database, filters, expected):
    engine = create_async_engine(seeded_database)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    try:
        async with session_factory() as session:
            total, items = await DocumentRepository(session).list(filters=filters)

        assert total == len(expected)
        assert [item["id"] for item in items] == expected
    finally:
        await engine.dispose()


def test_api_reads_real_database(db_client):
    response = db_client.get("/v1/documents/integration-001")

    assert response.status_code == 200
    assert response.json()["title"] == "Integration Test Document"


def test_loader_is_idempotent(database_url, tmp_path):
    record = {
        "id": "loader-test-001",
        "title": "Loader Integration Test",
        "situation": "Testing repeated loading",
    }

    data_file = tmp_path / "records.json"
    data_file.write_text(json.dumps([record]), encoding="utf-8")

    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    env["APP_ENV"] = "ci"
    env["DATA_FILE"] = str(data_file)

    first = subprocess.run(
        [sys.executable, "scripts/load_db.py"],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )

    second = subprocess.run(
        [sys.executable, "scripts/load_db.py"],
        capture_output=True,
        text=True,
        env=env,
        check=True,
    )

    assert "inserted=1" in first.stdout
    assert "unchanged=1" in second.stdout
