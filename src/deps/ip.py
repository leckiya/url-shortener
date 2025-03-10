from typing import Annotated

from aiohttp import ClientSession
from fastapi import Depends

from deps.config import Config
from log import logger


class LocationService:
    ipinfo_token: str

    def __init__(self, config: Annotated[Config, Depends(Config)]) -> None:
        self.ipinfo_token = config.ipinfo_token

    async def get_country(self, ip: str) -> str:
        async with ClientSession() as session:
            async with session.get(
                f"https://ipinfo.io/{ip}",
                headers={"Authorization": f"Bearer {self.ipinfo_token}"},
            ) as response:
                if response.status != 200:
                    logger.error(
                        f"ipinfo returning unexpected status code: {response.status}"
                    )
                    return "unknown"

                response = await response.json()
                if "country" not in response:
                    logger.error(f"ipinfo returning unexpected body: {response}")
                    return "unknown"

                return response["country"]
