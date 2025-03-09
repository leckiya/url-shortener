from fastapi import FastAPI

import controllers.webhook_service

app = FastAPI(title="Webhook service")


app.include_router(controllers.webhook_service.router)
