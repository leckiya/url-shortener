import unittest

from fastapi.testclient import TestClient

from webhook_svc import app


class TestApi(unittest.IsolatedAsyncioTestCase):
    client = TestClient(app)

    async def test_send_webhook(self):
        response = self.client.post(
            "/send",
            json={"id": "1", "url": "https://example.com", "body": {"key": "value"}},
        )
        self.assertEqual(response.status_code, 200)
