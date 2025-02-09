import unittest

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from database import set_engine, get_sessionmaker
from main import app
from models import Base, Url


class TestApi(unittest.IsolatedAsyncioTestCase):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    client = TestClient(app)

    async def asyncSetUp(self) -> None:
        set_engine(self.engine)
        async with self.engine.connect() as conn:
            await conn.run_sync(Base.metadata.create_all)

    async def asyncTearDown(self) -> None:
        async with self.engine.connect() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def test_create_new_url(self):
        response = self.client.post(
            "/urls", json={"key": "test", "target": "https://example.com"}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(), {"key": "test", "target": "https://example.com"}
        )

        response = self.client.post(
            "/urls", json={"key": "zulu", "target": "https://example.co.id"}
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(), {"key": "zulu", "target": "https://example.co.id"}
        )

        async with get_sessionmaker()() as session:
            stmt = select(Url).order_by(Url.key)
            result = await session.execute(stmt)

            self.assertEqual(
                list(result.scalars()),
                [
                    Url(key="test", target="https://example.com"),
                    Url(key="zulu", target="https://example.co.id"),
                ],
            )

    def test_create_new_url_invalid_input(self):
        for body in [
            {"key": "", "target": "https://example.com"},
            {"key": "test", "target": ""},
            {"key": "a" * 100, "target": "test"},
            {"key": "test", "target": "a" * 300},
            {"key": "test"},
            {"target": "test"},
            {},
        ]:
            response = self.client.post("/urls", json=body)
            self.assertEqual(response.status_code, 422, msg=body)

        result = self.client.get("/urls")
        self.assertEqual(result.json(), {"urls": []})

    def test_get_all(self):
        urls = [
            {"key": "a", "target": "https://example.com"},
            {"key": "b", "target": "https://example.co.id"},
        ]

        for url in reversed(urls):
            self.client.post("/urls", json=url)

        result = self.client.get("/urls")
        self.assertEqual(result.json(), {"urls": urls})

    def test_delete_url(self):
        url = {"key": "test", "target": "https://example.com"}
        response = self.client.post("/urls", json=url)
        self.assertEqual(response.status_code, 201)

        result = self.client.get("/urls")
        self.assertEqual(result.json(), {"urls": [url]})

        response = self.client.delete("/urls/test")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), url)

        result = self.client.get("/urls")
        self.assertEqual(result.json(), {"urls": []})

    def test_delete_url_does_not_exists(self):
        response = self.client.delete("/urls/test")
        self.assertEqual(response.status_code, 404)

    def test_delete_url_invalid_key(self):
        response = self.client.delete("/urls/" + "a" * 300)
        self.assertEqual(response.status_code, 422)

    def test_update_url(self):
        url = {"key": "test", "target": "https://example.com"}
        response = self.client.post("/urls", json=url)
        self.assertEqual(response.status_code, 201)

        result = self.client.get("/urls")
        self.assertEqual(result.json(), {"urls": [url]})

        new_url = {**url, "target": "https://example.co.id"}
        response = self.client.patch("/urls/test", json={"target": new_url["target"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), new_url)

        result = self.client.get("/urls")
        self.assertEqual(result.json(), {"urls": [new_url]})

    def test_update_missing_url(self):
        response = self.client.patch("/urls/test", json={"target": "invalid"})
        self.assertEqual(response.status_code, 404)

    def test_update_invalid_key(self):
        response = self.client.patch("/urls/" + "a" * 300, json={"target": "invalid"})
        self.assertEqual(response.status_code, 422)

    def test_update_invalid_inpute(self):
        for target in ["", "a" * 300, None]:
            response = self.client.patch("/urls/test", json={"target": target})
            self.assertEqual(response.status_code, 422)

    def test_redirect(self):
        url = {"key": "test", "target": "https://example.com"}
        response = self.client.post("/urls", json=url)
        self.assertEqual(response.status_code, 201)

        response = self.client.get("/redirect/test", follow_redirects=False)
        self.assertEqual(response.status_code, 308)
        self.assertEqual(response.headers.get("location"), "https://example.com")

    def test_redirect_missing(self):
        response = self.client.get("/redirect/test", follow_redirects=False)
        self.assertEqual(response.status_code, 404)

    def test_redirect_invalid_key(self):
        response = self.client.get("/redirect/" + "a" * 300, follow_redirects=False)
        self.assertEqual(response.status_code, 422)
