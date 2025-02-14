from fastapi import FastAPI

from controllers import router

app = FastAPI(title="URL Shortener")


app.include_router(router)
