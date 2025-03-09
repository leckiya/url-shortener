from typing import Annotated, Any

from aiohttp import ClientSession
from fastapi import Depends
from sqlalchemy.exc import NoResultFound

from deps.config import Config
from deps.database import SessionMaker
from log import logger
from models import Url, Webhook


class WebhookSender:
    session_maker: SessionMaker
    webhook_host: str

    def __init__(
        self,
        session_maker: Annotated[SessionMaker, Depends(SessionMaker)],
        config: Annotated[Config, Depends(Config)],
    ) -> None:
        self.session_maker = session_maker
        self.webhook_host = config.webhook_host

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

                try:
                    async with ClientSession() as session:
                        async with session.post(
                            f"{self.webhook_host}/send",
                            json={"url": webhook.url, "body": body},
                        ) as response:
                            if response.status != 200:
                                logger.error(
                                    f"failed to send webhook to {self.webhook_host} with"
                                    f" status code {response.status}"
                                )
                except Exception as e:
                    logger.error(f"failed to send webhook: {e}")
