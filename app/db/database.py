from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from core.config import settings


def _get_async_url(url: str) -> str:
    """Normalize the DATABASE_URL to always use the asyncpg driver."""
    # Replace any postgresql+psycopg, postgresql+psycopg2 or plain postgresql
    # with postgresql+asyncpg so we never need psycopg installed.
    for prefix in ("postgresql+psycopg2://", "postgresql+psycopg://", "postgresql://", "postgres://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


engine = create_async_engine(
    _get_async_url(settings.DATABASE_URL),
    pool_pre_ping=True,
    connect_args={"ssl": "require"},
)

SessionLocal = async_sessionmaker(bind=engine, expire_on_commit=False)


async def get_db():
    async with SessionLocal() as session:
        yield session
