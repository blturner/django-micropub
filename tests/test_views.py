import httpretty
import json

from django.test import Client, TestCase
from django.urls import reverse

from tests.models import Post


@httpretty.activate
class MicroPubTestCase(TestCase):
    def setUp(self):
        # httpretty.register_uri(
        #     httpretty.GET,
        #     "https://tokens.indieauth.com/token",
        #     body=b"me=https%3A%2F%2Fbenjaminturner.me%2F&issued_by=https%3A%2F%2Ftokens.indieauth.com%2Ftoken&client_id=https%3A%2F%2Fbenjaminturner.me&issued_at=1552542719&scope=&nonce=203045553",
        # )

        headers = {"HTTP_AUTHORIZATION": "Bearer 123"}

        self.client = Client(SERVER_NAME="example.com", **headers)
        self.endpoint = reverse("micropub")

    def test_create_entry(self):
        resp = self.client.post(self.endpoint, {"content": "bananas"})

        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.has_header("Location"))
        self.assertEqual(Post.objects.count(), 1)

        entry = Post.objects.get(id=1)

        self.assertEqual(entry.content, "bananas")
        # self.assertEqual(entry.status, "published")
        # self.assertEqual(entry.post_type, "note")

    def test_create_entry_json(self):
        data = {
            "type": ["h-entry"],
            "properties": {"content": ["hello world"]},
        }

        resp = self.client.post(
            self.endpoint,
            content_type="application/json",
            data=json.dumps(data),
        )

        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.has_header("Location"))
        self.assertEqual(Post.objects.count(), 1)

        entry = Post.objects.get(id=1)

        self.assertEqual(entry.content, "hello world")
        # self.assertEqual(entry.status, "published")
        # self.assertEqual(entry.post_type, "note")
