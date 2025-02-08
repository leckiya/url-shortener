from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, AsyncSession


def set_request_engine(request: Request, engine: AsyncEngine):
    request.state.engine = engine


def request_session(request: Request) -> AsyncSession:
    engine: AsyncEngine = request.state.engine
    session = async_sessionmaker(engine)
    return session()
