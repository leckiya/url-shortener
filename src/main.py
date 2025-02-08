from fastapi import FastAPI

app = FastAPI(title="URL Shortener")


@app.get("/")
def read_root():
    return {"Hello": "World"}
