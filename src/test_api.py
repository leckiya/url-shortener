import unittest
from typing import Any, Callable, TypeVar
from unittest.mock import Mock

import jwt
import jwt.utils
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.serialization import (
    Encoding,
    NoEncryption,
    PrivateFormat,
)
from fastapi.testclient import TestClient
from httpx import Request
from jwt.jwk_set_cache import JWKSetCache
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

from controllers import auth as auth_verifier
from deps.config import DEFAULT_ENV_FILES, load_config
from deps.database import get_sessionmaker, set_engine
from deps.ip import location_service
from main import app
from models import Base, Url

private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
public_key = private_key.public_key()


def auth(user: str = "testsuite") -> Callable[[Request], Request]:
    def wrapped_auth(req: Request) -> Request:
        req.headers["Authorization"] = "Bearer " + jwt.encode(
            {"sub": user, "iss": "testsuite", "aud": ["testsuite"]},
            private_key.private_bytes(
                Encoding.PEM, PrivateFormat.PKCS8, NoEncryption()
            ),
            algorithm="RS256",
            headers={"kid": "test"},
        )
        return req

    return wrapped_auth


def new_jwk_set_cache() -> JWKSetCache:
    cache = JWKSetCache(-1)
    numbers = public_key.public_numbers()

    n = jwt.utils.to_base64url_uint(numbers.n)
    e = jwt.utils.to_base64url_uint(numbers.e)

    x: Any = {
        "keys": [
            {
                "kty": "RSA",
                "use": "sig",
                "n": n,
                "e": e,
                "kid": "test",
            }
        ]
    }

    cache.put(x)
    return cache


location_service_mock = Mock()
app.dependency_overrides[location_service] = lambda: location_service_mock

T = TypeVar("T")


async def const_async(ret: T) -> T:
    return ret


class TestApi(unittest.IsolatedAsyncioTestCase):
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    client = TestClient(app)
    jwk_set_cache = new_jwk_set_cache()

    async def asyncSetUp(self) -> None:
        load_config(".env.test")

        set_engine(self.engine)
        auth_verifier.jwks_client.jwk_set_cache = self.jwk_set_cache
        async with self.engine.connect() as conn:
            await conn.run_sync(Base.metadata.create_all)

        global location_service_mock
        location_service_mock.get_country = lambda ip: const_async("test_country")

    async def asyncTearDown(self) -> None:
        load_config(DEFAULT_ENV_FILES)

        auth_verifier.jwks_client.jwk_set_cache = None
        async with self.engine.connect() as conn:
            await conn.run_sync(Base.metadata.drop_all)

    async def test_create_new_url_not_authenticated(self):
        response = self.client.post(
            "/urls", json={"key": "test", "target": "https://example.com"}
        )
        self.assertEqual(response.status_code, 403)

    async def test_create_new_url(self):
        response = self.client.post(
            "/urls", json={"key": "test", "target": "https://example.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(), {"key": "test", "target": "https://example.com"}
        )

        response = self.client.post(
            "/urls",
            json={"key": "zulu", "target": "https://example.co.id"},
            auth=auth(),
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
                    Url(owner="testing", key="test", target="https://example.com"),
                    Url(owner="testing", key="zulu", target="https://example.co.id"),
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
            response = self.client.post("/urls", json=body, auth=auth())
            self.assertEqual(response.status_code, 422, msg=body)

        result = self.client.get("/urls", auth=auth())
        self.assertEqual(result.json(), {"urls": []})

    def test_get_all_not_authenticated(self):
        response = self.client.get("/urls")
        self.assertEqual(response.status_code, 403)

    def test_get_all(self):
        urls = [
            {"owner": "user_1", "body": {"key": "a", "target": "https://example.com"}},
            {
                "owner": "user_2",
                "body": {"key": "b", "target": "https://example.co.id"},
            },
        ]

        for url in reversed(urls):
            self.client.post("/urls", json=url["body"], auth=auth(url["owner"]))

        result = self.client.get("/urls", auth=auth("user_1"))
        self.assertEqual(result.json(), {"urls": [urls[0]["body"]]})

    def test_delete_url_not_authenticated(self):
        response = self.client.delete("/urls/test")
        self.assertEqual(response.status_code, 403)

    def test_delete_url(self):
        url = {"key": "test", "target": "https://example.com"}
        response = self.client.post("/urls", json=url, auth=auth())
        self.assertEqual(response.status_code, 201)

        result = self.client.get("/urls", auth=auth())
        self.assertEqual(result.json(), {"urls": [url]})

        response = self.client.delete("/urls/test", auth=auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), url)

        result = self.client.get("/urls", auth=auth())
        self.assertEqual(result.json(), {"urls": []})

    def test_delete_url_other_user(self):
        url = {"key": "test", "target": "https://example.com"}
        response = self.client.post("/urls", json=url, auth=auth())
        self.assertEqual(response.status_code, 201)

        result = self.client.get("/urls", auth=auth())
        self.assertEqual(result.json(), {"urls": [url]})

        response = self.client.delete("/urls/test", auth=auth("other"))
        self.assertEqual(response.status_code, 404)

        result = self.client.get("/urls", auth=auth())
        self.assertEqual(result.json(), {"urls": [url]})

    def test_delete_url_does_not_exists(self):
        response = self.client.delete("/urls/test", auth=auth())
        self.assertEqual(response.status_code, 404)

    def test_delete_url_invalid_key(self):
        response = self.client.delete("/urls/" + "a" * 300, auth=auth())
        self.assertEqual(response.status_code, 422)

    def test_update_url_not_authenticated(self):
        response = self.client.patch("/urls/test", json={"target": ""})
        self.assertEqual(response.status_code, 403)

    def test_update_url(self):
        url = {"key": "test", "target": "https://example.com"}
        response = self.client.post("/urls", json=url, auth=auth())
        self.assertEqual(response.status_code, 201)

        result = self.client.get("/urls", auth=auth())
        self.assertEqual(result.json(), {"urls": [url]})

        new_url = {**url, "target": "https://example.co.id"}
        response = self.client.patch(
            "/urls/test", json={"target": new_url["target"]}, auth=auth()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), new_url)

        result = self.client.get("/urls", auth=auth())
        self.assertEqual(result.json(), {"urls": [new_url]})

    def test_update_url_other_user(self):
        url = {"key": "test", "target": "https://example.com"}
        response = self.client.post("/urls", json=url, auth=auth())
        self.assertEqual(response.status_code, 201)

        result = self.client.get("/urls", auth=auth())
        self.assertEqual(result.json(), {"urls": [url]})

        new_url = {**url, "target": "https://example.co.id"}
        response = self.client.patch(
            "/urls/test", json={"target": new_url["target"]}, auth=auth("other")
        )
        self.assertEqual(response.status_code, 404)

        result = self.client.get("/urls", auth=auth())
        self.assertEqual(result.json(), {"urls": [url]})

    def test_update_missing_url(self):
        response = self.client.patch(
            "/urls/test", json={"target": "invalid"}, auth=auth()
        )
        self.assertEqual(response.status_code, 404)

    def test_update_invalid_key(self):
        response = self.client.patch(
            "/urls/" + "a" * 300, json={"target": "invalid"}, auth=auth()
        )
        self.assertEqual(response.status_code, 422)

    def test_update_invalid_inpute(self):
        for target in ["", "a" * 300, None]:
            response = self.client.patch(
                "/urls/test", json={"target": target}, auth=auth()
            )
            self.assertEqual(response.status_code, 422)

    async def test_redirect(self):
        url = {"key": "test", "target": "https://example.com"}
        response = self.client.post("/urls", json=url, auth=auth())
        self.assertEqual(response.status_code, 201)

        for i in range(1, 6):
            response = self.client.get("/redirect/test", follow_redirects=False)
            self.assertEqual(response.status_code, 308)
            self.assertEqual(response.headers.get("location"), "https://example.com")

            response = self.client.get("/urls/test/statistic", auth=auth())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
                {"key": "test", "data": [{"country": "test_country", "count": i}]},
            )

        global location_service_mock
        location_service_mock.get_country = lambda _: const_async("test_country_2")

        for i in range(1, 6):
            response = self.client.get("/redirect/test", follow_redirects=False)
            self.assertEqual(response.status_code, 308)
            self.assertEqual(response.headers.get("location"), "https://example.com")

            response = self.client.get("/urls/test/statistic", auth=auth())
            self.assertEqual(response.status_code, 200)
            self.assertEqual(
                response.json(),
                {
                    "key": "test",
                    "data": [
                        {"country": "test_country", "count": 5},
                        {"country": "test_country_2", "count": i},
                    ],
                },
            )

    def test_redirect_missing(self):
        response = self.client.get("/redirect/test", follow_redirects=False)
        self.assertEqual(response.status_code, 404)

    def test_redirect_invalid_key(self):
        response = self.client.get("/redirect/" + "a" * 300, follow_redirects=False)
        self.assertEqual(response.status_code, 422)

    def test_suggest_not_authenticated(self):
        response = self.client.post("/suggest", json={"target": "https://example.com"})
        self.assertEqual(response.status_code, 403)

    def test_statistic_not_authenticated(self):
        response = self.client.get("/urls/test/statistic")
        self.assertEqual(response.status_code, 403)

    def test_statistic_not_found(self):
        response = self.client.get("/urls/test/statistic", auth=auth())
        self.assertEqual(response.status_code, 404)
