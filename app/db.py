from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from .config import settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.database_url, pool_pre_ping=True)
Session = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    from . import models  # noqa: F401  (registers tables)

    async with engine.begin() as conn:
        if engine.dialect.name == "sqlite":
            # Local preview only: an old demo file is simply rebuilt.
            columns = [row[1] for row in (await conn.exec_driver_sql("PRAGMA table_info(users)")).all()]
            events = [row[1] for row in (await conn.exec_driver_sql("PRAGMA table_info(events)")).all()]
            marks = [row[1] for row in (await conn.exec_driver_sql("PRAGMA table_info(attendance)")).all()]
            if ((columns and ("email" not in columns or "nudges" not in columns)) or (events and "image" not in events)
                    or (marks and "reminded" not in marks) or (columns and "source" not in columns)
                    or (columns and "gender" not in columns) or (marks and "girls_only" not in marks)):
                await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
        if engine.dialect.name == "postgresql":
            # Changes to tables that already exist on the server. Each line is safe to repeat.
            for statement in (
                "ALTER TABLE users ALTER COLUMN tg_id DROP NOT NULL",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS email VARCHAR(120)",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS password_hash VARCHAR(200) NOT NULL DEFAULT ''",
                "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_email ON users (email)",
                "ALTER TABLE events ADD COLUMN IF NOT EXISTS image VARCHAR(500) NOT NULL DEFAULT ''",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS nudges BOOLEAN NOT NULL DEFAULT TRUE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS last_nudge_at TIMESTAMP WITHOUT TIME ZONE",
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS reminded BOOLEAN NOT NULL DEFAULT FALSE",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS source VARCHAR(32) NOT NULL DEFAULT ''",
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS gender VARCHAR(1) NOT NULL DEFAULT ''",
                "ALTER TABLE attendance ADD COLUMN IF NOT EXISTS girls_only BOOLEAN NOT NULL DEFAULT FALSE",
            ):
                await conn.exec_driver_sql(statement)


async def get_session():
    async with Session() as session:
        yield session
