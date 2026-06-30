from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from core.config import settings


engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    connect_args={"ssl": "require"}
    )

SessionLocal = async_sessionmaker(
    bind=engine,
    expire_on_commit=False
)


async def get_db():
    async with SessionLocal() as session:
        yield session