from asyncio import BoundedSemaphore, Queue, wait_for
from typing import Any

from aiohttp import ClientSession
from fastapi import BackgroundTasks
from pydantic import BaseModel, Field, HttpUrl

from log import logger


class Webhook(BaseModel):
    url: HttpUrl = Field()
    body: Any = Field()


queue: Queue[Webhook] = Queue()
worker_permits = BoundedSemaphore(5)


class ExternalWebhookSender:
    """
    Queue and send webhooks.
    Known issue:
    - Webhook might be lost during service restart. Consider storing the queue in
      persistent storage.
    """

    background_tasks: BackgroundTasks

    def __init__(
        self,
        background_tasks: BackgroundTasks,
    ) -> None:
        self.background_tasks = background_tasks

    async def enqueue(self, webhook: Webhook):
        await queue.put(webhook)
        self.background_tasks.add_task(self.spawn_worker)

    async def spawn_worker(self):
        try:
            await wait_for(worker_permits.acquire(), 0.01)
        except TimeoutError:
            return

        try:
            logger.info(f"starting worker")
            while True:
                try:
                    webhook = await wait_for(queue.get(), 1.0)
                except TimeoutError:
                    break

                try:
                    async with ClientSession() as session:
                        async with session.post(
                            str(webhook.url),
                            json=webhook.body,
                        ) as response:
                            if response.status != 200:
                                logger.warning(
                                    f"failed to send webhook to {webhook.url} with"
                                    f" status code {response.status}"
                                )
                except Exception as e:
                    logger.warning(f"failed to send webhook: {e}")
        finally:
            worker_permits.release()
