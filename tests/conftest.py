from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from apps.core_service.app.db.base import Base
from apps.core_service.app.main import create_app
from apps.core_service.app.settings import Settings


@pytest.fixture
async def test_app(tmp_path) -> AsyncIterator:
    database_path = tmp_path / "test.db"
    settings = Settings(
        database_url=f"sqlite+aiosqlite:///{database_path.as_posix()}",
        task_id_node_id=7,
    )
    app = create_app(settings)

    async with app.router.lifespan_context(app):
        async with app.state.database_client.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield app


@pytest.fixture
async def async_client(test_app) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client
