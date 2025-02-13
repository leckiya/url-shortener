from typing import Union
from pydantic_settings import BaseSettings


class Config(BaseSettings):
    auth0_domain: str
    auth0_api_audience: str
    auth0_issuer: str
    auth0_algorithms: str

    def __init__(self, env_file: Union[str, list[str]]) -> None:
        super().__init__(_env_file=env_file)


DEFAULT_ENV_FILES = [".env.example", ".env"]
config = Config(env_file=DEFAULT_ENV_FILES)


def get_config():
    global config
    return config


def load_config(env_file: Union[str, list[str]]):
    global config
    config = Config(env_file=env_file)
    print(config)
