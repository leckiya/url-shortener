from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Security
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import delete, select, update
from sqlalchemy.exc import IntegrityError, NoResultFound

from auth import Jwt, VerifyToken
from database import SessionGetter, get_sessionmaker
from models import Url

router = APIRouter()
auth = VerifyToken()


KeyField = Field(min_length=1, max_length=64)
TargetField = Field(min_length=1, max_length=256)


class UrlObject(BaseModel):
    key: str = KeyField
    target: str = TargetField


def url_object_from_database(url: Url) -> UrlObject:
    return UrlObject(key=url.key, target=url.target)


class UrlObjects(BaseModel):
    urls: list[UrlObject]


@router.get(
    "/urls",
    response_model=UrlObjects,
    status_code=200,
)
async def get_all_url(
    get_session: Annotated[SessionGetter, Depends(get_sessionmaker)],
    jwt: Annotated[Jwt, Security(auth.verify)],
) -> UrlObjects:
    async with get_session() as session:
        async with session.begin():
            stmt = select(Url).where(Url.owner == jwt.sub).order_by(Url.key)
            results = await session.execute(stmt)
            return UrlObjects(
                urls=list(map(url_object_from_database, results.scalars()))
            )


@router.post(
    "/urls",
    response_model=UrlObject,
    status_code=201,
    responses={
        409: {"description": "Key already exists, use different key"},
    },
)
async def create_url(
    get_session: Annotated[SessionGetter, Depends(get_sessionmaker)],
    param: Annotated[UrlObject, Body()],
    jwt: Annotated[Jwt, Security(auth.verify)],
) -> UrlObject:
    try:
        new_url = Url(owner=jwt.sub, key=param.key, target=param.target)
        async with get_session() as session:
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
async def delete_url(
    get_session: Annotated[SessionGetter, Depends(get_sessionmaker)],
    key: Annotated[str, KeyField],
    jwt: Annotated[Jwt, Security(auth.verify)],
) -> UrlObject:
    async with get_session() as session:
        async with session.begin():
            stmt = (
                delete(Url)
                .where(Url.key == key)
                .where(Url.owner == jwt.sub)
                .returning(Url)
            )
            result = await session.execute(stmt)

            deleted = result.first()
            if deleted is None:
                raise HTTPException(status_code=404)

            print(deleted, jwt.sub)
            url: Url = deleted.Url
            return url_object_from_database(url)


class UrlUpdateChangeset(BaseModel):
    target: str = Field(min_length=1, max_length=256)


@router.patch(
    "/urls/{key}",
    response_model=UrlObject,
    status_code=200,
    responses={
        404: {"description": "Key does not exists"},
    },
)
async def update_url(
    get_session: Annotated[SessionGetter, Depends(get_sessionmaker)],
    key: Annotated[str, KeyField],
    param: Annotated[UrlUpdateChangeset, Body()],
    jwt: Annotated[Jwt, Security(auth.verify)],
) -> UrlObject:
    async with get_session() as session:
        async with session.begin():
            stmt = (
                update(Url)
                .where(Url.key == key)
                .where(Url.owner == jwt.sub)
                .values(target=param.target)
                .returning(Url)
            )
            result = await session.execute(stmt)
            updated = result.scalar_one_or_none()

            if updated is None:
                raise HTTPException(status_code=404)

            return url_object_from_database(updated)


@router.get(
    "/redirect/{key}",
    response_model=None,
    status_code=308,
    responses={404: {"description": "Key does not exists"}},
)
async def redirect(
    get_session: Annotated[SessionGetter, Depends(get_sessionmaker)],
    key: Annotated[str, KeyField],
) -> RedirectResponse:
    async with get_session() as session:
        async with session.begin():
            try:
                url = await session.get_one(Url, key)
                return RedirectResponse(url=url.target, status_code=308)
            except NoResultFound:
                raise HTTPException(status_code=404)
