from typing import Annotated

from fastapi import APIRouter, Body, Depends, HTTPException, Security
from pydantic import BaseModel, Field, HttpUrl
from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import NoResultFound

from auth import Jwt, verify_token
from deps.database import SessionMaker
from models import Webhook

router = APIRouter()


class WebhookObject(BaseModel):
    url: HttpUrl = Field()


@router.get("/webhooks", responses={404: {"description": "webhook is not set"}})
async def get_webhook(
    session_maker: Annotated[SessionMaker, Depends(SessionMaker)],
    jwt: Annotated[Jwt, Security(verify_token)],
) -> WebhookObject:
    async with session_maker() as session:
        async with session.begin():
            try:
                webhook = await session.get_one(Webhook, jwt.sub)
                return WebhookObject(url=HttpUrl(webhook.url))
            except NoResultFound:
                raise HTTPException(status_code=404)


@router.post("/webhooks")
async def set_webhook(
    session_maker: Annotated[SessionMaker, Depends(SessionMaker)],
    jwt: Annotated[Jwt, Security(verify_token)],
    param: Annotated[WebhookObject, Body()],
) -> WebhookObject:
    async with session_maker() as session:
        async with session.begin():
            stmt = insert(Webhook).values(user=jwt.sub, url=str(param.url))
            stmt = stmt.on_conflict_do_update(
                index_elements=[Webhook.user], set_=dict(url=str(param.url))
            )
            await session.execute(stmt)

    return param


@router.delete("/webhooks")
async def delete_webhook(
    session_maker: Annotated[SessionMaker, Depends(SessionMaker)],
    jwt: Annotated[Jwt, Security(verify_token)],
):
    async with session_maker() as session:
        async with session.begin():
            stmt = delete(Webhook).where(Webhook.user == jwt.sub)
            await session.execute(stmt)
