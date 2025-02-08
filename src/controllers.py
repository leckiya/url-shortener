from typing import Annotated
from fastapi import APIRouter, Body, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlalchemy.exc import IntegrityError
from models import Url
from database import request_session


router = APIRouter()


class UrlObject(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    target: str = Field(min_length=1, max_length=256)


@router.post(
    "/urls",
    response_model=UrlObject,
    status_code=201,
    responses={
        409: {"description": "Key already exists, use different key"},
    },
)
async def create_url(
    request: Request, param: Annotated[UrlObject, Body()]
) -> UrlObject:
    try:
        new_url = Url(key=param.key, target=param.target)
        async with request_session(request) as session:
            async with session.begin():
                session.add_all([new_url])
    except IntegrityError:
        raise HTTPException(status_code=409)

    return param


@router.delete(
    "/urls/{key}",
    response_model=UrlObject,
    status_code=200,
    responses={
        404: {"description": "Key does not exists"},
    },
)
async def delete_url(request: Request, key: str) -> UrlObject:
    async with request_session(request) as session:
        async with session.begin():
            stmt = delete(Url).where(Url.key == key).returning(Url)
            result = await session.execute(stmt)

            deleted = result.first()
            if deleted is None:
                raise HTTPException(status_code=404)

            url: Url = deleted.Url
            return UrlObject(key=url.key, target=url.target)
