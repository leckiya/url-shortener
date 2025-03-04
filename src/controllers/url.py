from typing import Annotated, List

from fastapi import APIRouter, Body, Depends, HTTPException, Request, Security
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import delete, distinct, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError, NoResultFound
from sqlalchemy.orm import selectinload
from sqlalchemy.sql.functions import count

from auth import Jwt
from controllers import auth
from deps.database import SessionGetter, get_sessionmaker
from deps.ip import LocationService, location_service
from deps.openai import get_recommendation
from deps.webhook_sender import WebhookSender
from models import Url, UrlRedirectUsage

router = APIRouter()


KeyField = Field(min_length=1, max_length=64, pattern=r"^[a-z\d\-_]+$")
TargetField = Field(min_length=1, max_length=256)


class UrlObject(BaseModel):
    key: str = KeyField
    target: HttpUrl = TargetField


def url_object_from_database(url: Url) -> UrlObject:
    return UrlObject(key=url.key, target=HttpUrl(url.target))


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
    webhook_sender: Annotated[WebhookSender, Depends(WebhookSender)],
    param: Annotated[UrlObject, Body()],
    jwt: Annotated[Jwt, Security(auth.verify)],
) -> UrlObject:
    try:
        new_url = Url(owner=jwt.sub, key=param.key, target=str(param.target))
        async with get_session() as session:
            async with session.begin():
                session.add_all([new_url])
                await webhook_sender.link_created(new_url)
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
    webhook_sender: Annotated[WebhookSender, Depends(WebhookSender)],
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

            url: Url = deleted.Url
            await webhook_sender.link_deleted(url)
            return url_object_from_database(url)


class UrlUpdateChangeset(BaseModel):
    target: HttpUrl = TargetField


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
    webhook_sender: Annotated[WebhookSender, Depends(WebhookSender)],
    key: Annotated[str, KeyField],
    param: Annotated[UrlUpdateChangeset, Body()],
    jwt: Annotated[Jwt, Security(auth.verify)],
) -> UrlObject:
    print(param)
    async with get_session() as session:
        async with session.begin():
            stmt = (
                update(Url)
                .where(Url.key == key)
                .where(Url.owner == jwt.sub)
                .values(target=str(param.target))
                .returning(Url)
            )
            result = await session.execute(stmt)
            updated = result.scalar_one_or_none()

            if updated is None:
                raise HTTPException(status_code=404)

            await webhook_sender.link_updated(updated)
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
    location_service: Annotated[LocationService, Depends(location_service)],
    webhook_sender: Annotated[WebhookSender, Depends(WebhookSender)],
    request: Request,
) -> RedirectResponse:
    country = "unknown"

    ip = request.headers.get("X-Forwarded-For")
    if ip is None and request.client is not None:
        ip = request.client.host

    if ip is not None:
        country = await location_service.get_country(ip)

    async with get_session() as session:
        async with session.begin():
            try:
                url = await session.get_one(Url, key)
                analytics_stmt = insert(UrlRedirectUsage).values(
                    url_key=url.key, country=country
                )
                analytics_stmt = analytics_stmt.on_conflict_do_update(
                    index_elements=[UrlRedirectUsage.url_key, UrlRedirectUsage.country],
                    set_=dict(count=(UrlRedirectUsage.count + 1)),
                )
                await session.execute(analytics_stmt)
                await webhook_sender.link_clicked(url)
                return RedirectResponse(url=url.target, status_code=308)
            except NoResultFound:
                raise HTTPException(status_code=404)


class UrlStatisticPerCountry(BaseModel):
    country: str = Field()
    count: int = Field()


class UrlStatisticResponse(BaseModel):
    key: str = KeyField
    data: List[UrlStatisticPerCountry] = Field()


@router.get(
    "/urls/{key}/statistic",
    response_model=UrlStatisticResponse,
    responses={404: {"description": "Key does not exists"}},
)
async def get_url_statistic(
    get_session: Annotated[SessionGetter, Depends(get_sessionmaker)],
    key: Annotated[str, KeyField],
    jwt: Annotated[Jwt, Security(auth.verify)],
) -> UrlStatisticResponse:
    async with get_session() as session:
        async with session.begin():
            try:
                stmt = (
                    select(Url)
                    .where(Url.key == key)
                    .where(Url.owner == jwt.sub)
                    .options(selectinload(Url.url_redirect_usages))
                )
                result = await session.execute(stmt)
                url = result.scalar_one()
                usages = url.url_redirect_usages
                usages = list(
                    map(
                        lambda i: UrlStatisticPerCountry(
                            country=i.country, count=i.count
                        ),
                        usages,
                    )
                )
                usages.sort(key=lambda i: i.country)
                return UrlStatisticResponse(
                    key=url.key,
                    data=usages,
                )
            except NoResultFound:
                raise HTTPException(status_code=404)


class SuggestionRequest(BaseModel):
    target: str = TargetField


class SuggestionResponse(BaseModel):
    key: str


@router.post(
    "/suggest",
    status_code=200,
)
async def suggest(
    request: Annotated[SuggestionRequest, Body()],
    jwt: Annotated[Jwt, Security(auth.verify)],
) -> SuggestionResponse:
    return SuggestionResponse(key=await get_recommendation(request.target))


class StatisticResponse(BaseModel):
    n_links: int = Field()
    n_user: int = Field()


@router.get("/statistic")
async def statistic(
    get_session: Annotated[SessionGetter, Depends(get_sessionmaker)],
) -> StatisticResponse:
    async with get_session() as session:
        async with session.begin():
            stmt = select(count(Url.key), count(distinct(Url.owner)))
            result = await session.execute(stmt)

            [n_links, n_user] = result.one()
            return StatisticResponse(n_links=n_links, n_user=n_user)
