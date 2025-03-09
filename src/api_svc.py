from fastapi import FastAPI

import controllers.url
import controllers.webhook_management

app = FastAPI(title="URL Shortener")


app.include_router(controllers.url.router)
app.include_router(controllers.webhook_management.router)
