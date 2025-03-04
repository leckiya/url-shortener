from typing import Annotated, Optional

import requests
from fastapi import Depends
from sqlalchemy.exc import NoResultFound
from sqlalchemy.ext.asyncio import AsyncSession

from deps.database import SessionGetter, get_sessionmaker
from log import logger
from models import Url, Webhook


class WebhookSender:
    get_session: SessionGetter

    def __init__(
        self, get_session: Annotated[SessionGetter, Depends(get_sessionmaker)]
    ) -> None:
        self.get_session = get_session

    async def link_clicked(self, url: Url):
        async with self.get_session() as session:
            async with session.begin():
                webhook = await fetch_webhook(session, url.owner)
                if webhook is None:
                    return

                response = requests.post(
                    webhook.url, json={"action": "redirect", "key": url.key}
                )
                if response.status_code != 200:
                    logger.warning(
                        f"failed to send webhook to {webhook.url} with"
                        f" status code {response.status_code}"
                    )


async def fetch_webhook(session: AsyncSession, user: str) -> Optional[Webhook]:
    try:
        return await session.get_one(Webhook, user)
    except NoResultFound:
        return None
