import unittest

from aioresponses import aioresponses

from deps.config import Config
from deps.ip import LocationService


class TestLocationService(unittest.IsolatedAsyncioTestCase):
    config: Config
    service: LocationService

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)

        self.config = Config([".env.test"])
        self.assertGreater(len(self.config.ipinfo_token), 0)
        self.service = LocationService(self.config)

    def assert_auth_header(self, url, headers, **kwargs):
        self.assertEqual(
            headers, {"Authorization": f"Bearer {self.config.ipinfo_token}"}
        )

    async def test_location_service_ok(self):
        with aioresponses() as m:
            m.get(
                "https://ipinfo.io/127.0.0.1",
                payload={"country": "Singapore"},
                callback=self.assert_auth_header,
            )
            country = await self.service.get_country("127.0.0.1")
            self.assertEqual(country, "Singapore")

    async def test_location_service_invalid_token(self):
        with aioresponses() as m:
            m.get(
                "https://ipinfo.io/127.0.0.1",
                status=403,
                callback=self.assert_auth_header,
            )
            country = await self.service.get_country("127.0.0.1")
            self.assertEqual(country, "unknown")

    async def test_location_service_unknown_location(self):
        with aioresponses() as m:
            m.get(
                "https://ipinfo.io/127.0.0.1",
                status=404,
                callback=self.assert_auth_header,
            )
            country = await self.service.get_country("127.0.0.1")
            self.assertEqual(country, "unknown")

    async def test_location_service_unexpected_body(self):
        with aioresponses() as m:
            m.get(
                "https://ipinfo.io/127.0.0.1",
                payload={"other": "Singapore"},
                callback=self.assert_auth_header,
            )
            country = await self.service.get_country("127.0.0.1")
            self.assertEqual(country, "unknown")
