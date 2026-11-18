"""Check the PostgreSQL database connection."""

import asyncio

from sqlalchemy import text

from flyright.config import get_settings
from flyright.db.session import make_engine


async def main() -> None:
    engine = make_engine(get_settings())

    try:
        async with engine.connect() as connection:
            result = await connection.execute(text("SELECT current_database(), version()"))
            database, version = result.one()

            print(f"Connected to database '{database}'")
            print(version)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
