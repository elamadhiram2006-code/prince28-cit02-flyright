from sqlalchemy.engine import make_url

from flyright.db.url import to_asyncpg_url


def test_converts_postgres_url_to_asyncpg():
    result = make_url(to_asyncpg_url("postgres://localhost:5432/flyright"))

    assert result.drivername == "postgresql+asyncpg"


def test_converts_psycopg2_and_ssl_parameters():
    raw = "postgresql+psycopg2://localhost/flyright?sslmode=require&channel_binding=require"

    result = make_url(to_asyncpg_url(raw))

    assert result.drivername == "postgresql+asyncpg"
    assert result.query["ssl"] == "require"
    assert "sslmode" not in result.query
    assert "channel_binding" not in result.query


def test_preserves_asyncpg_and_removes_disabled_ssl():
    raw = "postgresql+asyncpg://localhost/flyright?sslmode=disable&channel_binding=require"

    result = make_url(to_asyncpg_url(raw))

    assert result.drivername == "postgresql+asyncpg"
    assert "sslmode" not in result.query
    assert "channel_binding" not in result.query
    assert "ssl" not in result.query
