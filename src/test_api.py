import json
import unittest
from typing import Any, Callable, TypeVar
from unittest.mock import Mock

import httpretty
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
from sqlalchemy.ext.asyncio import create_async_engine

from auth import JwksClient
from deps.config import Config
from deps.database import engine_builder
from deps.ip import LocationService
from main import app
from models import Base

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


config = Config([".env.test"])
jwks_client = JwksClient(config)
jwk_set_cache = new_jwk_set_cache()
jwks_client.client.jwk_set_cache = jwk_set_cache

engine = create_async_engine("sqlite+aiosqlite:///:memory:")

location_service_mock = Mock()
app.dependency_overrides[LocationService] = lambda: location_service_mock
app.dependency_overrides[Config] = lambda: config
app.dependency_overrides[JwksClient] = lambda: jwks_client
app.dependency_overrides[engine_builder] = lambda: engine

T = TypeVar("T")


async def const_async(ret: T) -> T:
    return ret


class TestApi(unittest.IsolatedAsyncioTestCase):
    client = TestClient(app)

    async def asyncSetUp(self) -> None:
        async with engine.connect() as conn:
            await conn.run_sync(Base.metadata.create_all)

        global location_service_mock
        location_service_mock.get_country = lambda ip: const_async("test_country")

    async def asyncTearDown(self) -> None:
        async with engine.connect() as conn:
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
            response.json(), {"key": "test", "target": "https://example.com/"}
        )

        response = self.client.post(
            "/urls",
            json={"key": "zulu", "target": "https://example.co.id/"},
            auth=auth(),
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(), {"key": "zulu", "target": "https://example.co.id/"}
        )

        response = self.client.get("/urls", auth=auth())
        self.assertEqual(
            response.json(),
            {
                "urls": [
                    {
                        "key": "test",
                        "target": "https://example.com/",
                    },
                    {
                        "key": "zulu",
                        "target": "https://example.co.id/",
                    },
                ],
            },
        )

    def test_create_new_url_invalid_input(self):
        for body in [
            {"key": "Test", "target": "https://example.com"},
            {"key": "t*st", "target": "https://example.com"},
            {"key": "test", "target": "fff://example.com"},
            {"key": "test", "target": "https://ex^mple.com"},
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
            {"owner": "user_1", "body": {"key": "a", "target": "https://example.com/"}},
            {
                "owner": "user_2",
                "body": {"key": "b", "target": "https://example.co.id/"},
            },
        ]

        for url in reversed(urls):
            response = self.client.post(
                "/urls", json=url["body"], auth=auth(url["owner"])
            )
            self.assertEqual(response.status_code, 201)

        result = self.client.get("/urls", auth=auth("user_1"))
        self.assertEqual(result.json(), {"urls": [urls[0]["body"]]})

    def test_delete_url_not_authenticated(self):
        response = self.client.delete("/urls/test")
        self.assertEqual(response.status_code, 403)

    def test_delete_url(self):
        url = {"key": "test", "target": "https://example.com/"}
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
        url = {"key": "test", "target": "https://example.com/"}
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
        url = {"key": "test", "target": "https://example.com/"}
        response = self.client.post("/urls", json=url, auth=auth())
        self.assertEqual(response.status_code, 201)

        result = self.client.get("/urls", auth=auth())
        self.assertEqual(result.json(), {"urls": [url]})

        new_url = {**url, "target": "https://example.co.id/"}
        response = self.client.patch(
            "/urls/test", json={"target": new_url["target"]}, auth=auth()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), new_url)

        result = self.client.get("/urls", auth=auth())
        self.assertEqual(result.json(), {"urls": [new_url]})

    def test_update_url_other_user(self):
        url = {"key": "test", "target": "https://example.com/"}
        response = self.client.post("/urls", json=url, auth=auth())
        self.assertEqual(response.status_code, 201)

        result = self.client.get("/urls", auth=auth())
        self.assertEqual(result.json(), {"urls": [url]})

        new_url = {**url, "target": "https://example.co.id/"}
        response = self.client.patch(
            "/urls/test", json={"target": new_url["target"]}, auth=auth("other")
        )
        self.assertEqual(response.status_code, 404)

        result = self.client.get("/urls", auth=auth())
        self.assertEqual(result.json(), {"urls": [url]})

    def test_update_missing_url(self):
        response = self.client.patch(
            "/urls/test", json={"target": "https://example.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 404)

    def test_update_invalid_key(self):
        response = self.client.patch(
            "/urls/" + "a" * 300, json={"target": "https://example.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 422)

    def test_update_invalid_inpute(self):
        for target in ["", "a" * 300, None, "f://example.com", "https://ex^mple.com"]:
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
            self.assertEqual(response.headers.get("location"), "https://example.com/")

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
            self.assertEqual(response.headers.get("location"), "https://example.com/")

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

    def test_statistic(self):
        response = self.client.get("/statistic")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"n_links": 0, "n_user": 0})

        url = {"key": "test", "target": "https://example.com"}
        response = self.client.post("/urls", json=url, auth=auth())
        self.assertEqual(response.status_code, 201)

        response = self.client.get("/statistic")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"n_links": 1, "n_user": 1})

        url = {"key": "test_2", "target": "https://example.com"}
        response = self.client.post("/urls", json=url, auth=auth("other_user"))
        self.assertEqual(response.status_code, 201)

        response = self.client.get("/statistic")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"n_links": 2, "n_user": 2})

        url = {"key": "test_3", "target": "https://example.com"}
        response = self.client.post("/urls", json=url, auth=auth("other_user"))
        self.assertEqual(response.status_code, 201)

        response = self.client.get("/statistic")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"n_links": 3, "n_user": 2})

    def test_set_webhook_not_authenticated(self):
        response = self.client.post(
            "/webhooks", json={"url": "https://example.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://example.com/"})

        response = self.client.get("/webhooks", auth=auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://example.com/"})

        response = self.client.post("/webhooks", json={"url": "https://example2.com"})
        self.assertEqual(response.status_code, 403)

        response = self.client.get("/webhooks", auth=auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://example.com/"})

    def test_set_webhook(self):
        response = self.client.post(
            "/webhooks", json={"url": "https://example.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://example.com/"})

        response = self.client.get("/webhooks", auth=auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://example.com/"})

    def test_set_webhook_invalid_url(self):
        response = self.client.post(
            "/webhooks", json={"url": "https://example.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://example.com/"})

        response = self.client.get("/webhooks", auth=auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://example.com/"})

        response = self.client.post(
            "/webhooks", json={"url": "https://ex^mple.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 422)

        response = self.client.get("/webhooks", auth=auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://example.com/"})

    def test_get_webhook_not_authenticated(self):
        response = self.client.get("/webhooks")
        self.assertEqual(response.status_code, 403)

    def test_get_webhook(self):
        response = self.client.get("/webhooks", auth=auth())
        self.assertEqual(response.status_code, 404)

        response = self.client.post(
            "/webhooks", json={"url": "https://example.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://example.com/"})

        response = self.client.get("/webhooks", auth=auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://example.com/"})

    def test_delete_webhook(self):
        response = self.client.post(
            "/webhooks", json={"url": "https://example.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://example.com/"})

        response = self.client.get("/webhooks", auth=auth())
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://example.com/"})

        for _ in range(2):
            response = self.client.delete("/webhooks", auth=auth())
            self.assertEqual(response.status_code, 200)

            response = self.client.get("/webhooks", auth=auth())
            self.assertEqual(response.status_code, 404)

    @httpretty.activate()
    def test_webhook_on_redirect(self):
        httpretty.register_uri(httpretty.POST, "https://webhook.com")

        response = self.client.post(
            "/webhooks", json={"url": "https://webhook.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://webhook.com/"})

        response = self.client.post(
            "/urls", json={"key": "test", "target": "https://example.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(), {"key": "test", "target": "https://example.com/"}
        )

        response = self.client.get("/redirect/test", follow_redirects=False)
        self.assertEqual(response.status_code, 308)
        self.assertEqual(response.headers.get("location"), "https://example.com/")

        body = json.loads(httpretty.last_request().body)
        self.assertEqual(body, {"action": "redirect", "key": "test"})

    @httpretty.activate()
    def test_webhook_on_create(self):
        httpretty.register_uri(httpretty.POST, "https://webhook.com")

        response = self.client.post(
            "/webhooks", json={"url": "https://webhook.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://webhook.com/"})

        response = self.client.post(
            "/urls", json={"key": "test", "target": "https://example.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(), {"key": "test", "target": "https://example.com/"}
        )

        body = json.loads(httpretty.last_request().body)
        self.assertEqual(
            body,
            {"action": "created", "key": "test", "target": "https://example.com/"},
        )

    @httpretty.activate()
    def test_webhook_on_delete(self):
        httpretty.register_uri(httpretty.POST, "https://webhook.com")

        response = self.client.post(
            "/webhooks", json={"url": "https://webhook.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://webhook.com/"})

        response = self.client.post(
            "/urls", json={"key": "test", "target": "https://example.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(), {"key": "test", "target": "https://example.com/"}
        )

        response = self.client.delete("/urls/test", auth=auth())
        self.assertEqual(response.status_code, 200)

        body = json.loads(httpretty.last_request().body)
        self.assertEqual(
            body,
            {"action": "deleted", "key": "test", "target": "https://example.com/"},
        )

    @httpretty.activate()
    def test_webhook_on_update(self):
        httpretty.register_uri(httpretty.POST, "https://webhook.com")

        response = self.client.post(
            "/webhooks", json={"url": "https://webhook.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"url": "https://webhook.com/"})

        response = self.client.post(
            "/urls", json={"key": "test", "target": "https://example.com"}, auth=auth()
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(
            response.json(), {"key": "test", "target": "https://example.com/"}
        )

        response = self.client.patch(
            "/urls/test", json={"target": "https://example-2.com/"}, auth=auth()
        )
        self.assertEqual(response.status_code, 200)

        body = json.loads(httpretty.last_request().body)
        self.assertEqual(
            body,
            {
                "action": "deleted",
                "key": "test",
                "new_target": "https://example-2.com/",
            },
        )
