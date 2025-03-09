from typing import Annotated

from fastapi import APIRouter, Body, Depends

from deps.external_webhook_sender import ExternalWebhookSender, Webhook

router = APIRouter()


@router.post("/send")
async def send_webhook(
    external_webhook_sender: Annotated[
        ExternalWebhookSender, Depends(ExternalWebhookSender)
    ],
    webhook: Annotated[Webhook, Body()],
):
    await external_webhook_sender.enqueue(webhook)
