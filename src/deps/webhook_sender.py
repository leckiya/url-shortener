from typing import Annotated, Any

import requests
from fastapi import Depends
from sqlalchemy.exc import NoResultFound

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
        await self._send(url.owner, {"action": "redirect", "key": url.key})

    async def link_created(self, url: Url):
        await self._send(
            url.owner, {"action": "created", "key": url.key, "target": url.target}
        )

    async def link_deleted(self, url: Url):
        await self._send(
            url.owner, {"action": "deleted", "key": url.key, "target": url.target}
        )

    async def _send(self, user: str, body: Any):
        async with self.get_session() as session:
            async with session.begin():
                try:
                    webhook = await session.get_one(Webhook, user)
                except NoResultFound:
                    return

                response = requests.post(
                    webhook.url,
                    json=body,
                )
                if response.status_code != 200:
                    logger.warning(
                        f"failed to send webhook to {webhook.url} with"
                        f" status code {response.status_code}"
                    )
