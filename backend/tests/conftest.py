import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///:memory:")

try:
    from httpx import AsyncClient, ASGITransport
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
    import main as backend_main
    from app.api.deps import get_db
    from app.core.database import Base
    import app.db.base  # noqa: F401
    app = backend_main.app
    _WEB_STACK_AVAILABLE = True
except ImportError:
    _WEB_STACK_AVAILABLE = False

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"


@pytest.fixture(scope="session")
async def test_engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        # Import all models so Base.metadata knows about them
        import app.db.base  # noqa: F401
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(test_engine):
    async_session = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        yield session


@pytest.fixture
async def client(db_session):
    async def override_get_db():
        yield db_session
    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def auth_headers() -> dict:
    from app.core.security import create_access_token
    token = create_access_token({"sub": "testuser"})
    return {"Authorization": f"Bearer {token}"}
