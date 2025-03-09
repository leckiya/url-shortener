from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from deps.config import Config

engine = None


def engine_builder(config: Annotated[Config, Depends(Config)]):
    global engine
    if engine is not None:
        return engine

    engine = create_async_engine(postgres_url(config), pool_size=20)
    return engine


class SessionMaker:
    sessionmaker: async_sessionmaker

    def __init__(self, engine: Annotated[AsyncEngine, Depends(engine_builder)]) -> None:
        self.sessionmaker = async_sessionmaker(engine)

    def __call__(self) -> AsyncSession:
        return self.sessionmaker()


def postgres_url(config: Config, is_async: bool = True) -> str:
    async_flag = "+asyncpg" if is_async else ""
    return (
        f"postgresql{async_flag}://{config.postgres_user}:{config.postgres_password}"
        f"@{config.postgres_host}:{config.postgres_port}/{config.postgres_database}"
    )
