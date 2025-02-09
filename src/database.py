import os
from typing import Callable, Optional
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    AsyncSession,
    create_async_engine,
)
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
        db_url = os.environ.get("URLS_DB_URL")
        if db_url is None:
            logger.error("URLS_DB_URL is not set")
            exit(1)
        db_engine = create_async_engine(db_url, pool_size=20)
        set_engine(db_engine)

    assert sessionmaker is not None
    return sessionmaker
