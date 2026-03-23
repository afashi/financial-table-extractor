from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


class DatabaseClient:
    def __init__(self, database_url: str) -> None:
        self.engine: AsyncEngine = create_async_engine(
            database_url,
            echo=False,
            pool_pre_ping=True,
        )
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def healthcheck(self) -> None:
        async with self.engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def dispose(self) -> None:
        await self.engine.dispose()
