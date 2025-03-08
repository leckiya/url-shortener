from typing import Annotated, Any

import requests
from fastapi import Depends
from sqlalchemy.exc import NoResultFound

from deps.database import SessionMaker
from log import logger
from models import Url, Webhook


class WebhookSender:
    session_maker: SessionMaker

    def __init__(
        self, get_session: Annotated[SessionMaker, Depends(SessionMaker)]
    ) -> None:
        self.session_maker = get_session

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

    async def link_updated(self, url: Url):
        await self._send(
            url.owner, {"action": "deleted", "key": url.key, "new_target": url.target}
        )

    async def _send(self, user: str, body: Any):
        async with self.session_maker() as session:
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
