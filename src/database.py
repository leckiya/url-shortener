from typing import Callable, Optional

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from config import get_config
from log import logger

db_engine: Optional[AsyncEngine] = None
sessionmaker: Optional[async_sessionmaker] = None


SessionGetter = Callable[[], AsyncSession]


def set_engine(engine: AsyncEngine) -> None:
    global db_engine, sessionmaker
    db_engine = engine
    sessionmaker = async_sessionmaker(engine)


def get_sessionmaker() -> async_sessionmaker:
    global engine, sessionmaker
    if sessionmaker is None:
        logger.info("initializing db_engine")
        db_engine = create_async_engine(postgres_url(), pool_size=20)
        set_engine(db_engine)

    assert sessionmaker is not None
    return sessionmaker


def postgres_url(is_async: bool = True) -> str:
    config = get_config()
    async_flag = "+asyncpg" if is_async else ""
    return (
        f"postgresql{async_flag}://{config.postgres_user}:{config.postgres_password}"
        f"@{config.postgres_host}:{config.postgres_port}/{config.postgres_database}"
    )
