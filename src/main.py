import os
from typing import Optional

from fastapi import FastAPI, Request
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from log import logger
from controllers import router
from database import set_request_engine


app = FastAPI(title="URL Shortener")
db_engine: Optional[AsyncEngine] = None


def set_engine(engine: AsyncEngine) -> None:
    global db_engine
    db_engine = engine


def get_engine() -> AsyncEngine:
    global db_engine
    if db_engine is not None:
        return db_engine

    logger.info("initializing db_engine")
    db_url = os.environ.get("URLS_DB_URL")
    if db_url is None:
        logger.error("URLS_DB_URL is not set")
        exit(1)
    db_engine = create_async_engine(db_url, pool_size=20)
    return db_engine


@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    set_request_engine(request, get_engine())
    response = await call_next(request)
    return response


app.include_router(router)
