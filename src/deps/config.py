from typing import Annotated

from fastapi import Depends
from pydantic_settings import BaseSettings

DEFAULT_ENV_FILES = ["../.env", ".env"]


def env_files() -> list[str]:
    return DEFAULT_ENV_FILES


class Config(BaseSettings):
    auth0_domain: str
    auth0_api_audience: str
    auth0_issuer: str
    auth0_algorithms: str

    postgres_user: str
    postgres_password: str
    postgres_host: str
    postgres_port: int
    postgres_database: str

    openai_key: str

    ipinfo_token: str

    webhook_host: str

    def __init__(self, env_file: Annotated[list[str], Depends(env_files)]) -> None:
        super().__init__(_env_file=env_file)
