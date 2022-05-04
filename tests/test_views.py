import httpretty
import json

from urllib.parse import urlparse, urlencode

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.urls import reverse

from micropub.models import IndieAuth

from tests.models import Post


class IndieLoginTestCase(TestCase):
    def setUp(self):
        self.client.force_login(user=self.user)

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create(username="fred", password="secret")

    def test_create_login(self):
        resp = self.client.post(
            reverse("micropub-login"),
            {
                "url": "https://example.com",
                "client_id": "https://example.com",
                "redirect_uri": "https://example.com/callback",
                "state": "123",
                "user": self.user.id,
            },
        )
        qs = urlencode(
            {
                "client_id": "https://example.com",
                "redirect_uri": "https://example.com/callback",
                "state": "123",
            }
        )
        redirect_url = f"https://indielogin.com/auth?{qs}"
        indie_auth = IndieAuth.objects.get(user__id=self.user.id)

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, redirect_url)
        self.assertEqual(indie_auth.state, "123")

    def test_callback_code(self):
        IndieAuth.objects.create(user=self.user, state="123")
        resp = self.client.get(
            reverse("micropub-verify"),
            {"state": "123", "code": "456"},
        )
        indie_auth = IndieAuth.objects.get(user__id=self.user.id)

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(indie_auth.state, "123")
        self.assertEqual(indie_auth.code, "456")


@httpretty.activate
class MicroPubTestCase(TestCase):
    def setUp(self):
        httpretty.register_uri(
            httpretty.GET,
            "https://tokens.indieauth.com/token",
            body=b"me=https%3A%2F%2Fbenjaminturner.me%2F&issued_by=https%3A%2F%2Ftokens.indieauth.com%2Ftoken&client_id=https%3A%2F%2Fbenjaminturner.me&issued_at=1552542719&scope=&nonce=203045553",
        )

        headers = {"HTTP_AUTHORIZATION": "Bearer 123"}

        self.client = Client(SERVER_NAME="example.com", **headers)
        self.endpoint = reverse("micropub")

    def test_create_entry(self):
        resp = self.client.post(
            self.endpoint,
            {
                "h": "entry",
                "content": "bananas",
            },
        )

        self.assertEqual(resp.status_code, 201)

        post = Post.objects.get(content="bananas")

        self.assertEqual(
            urlparse(resp.get("location")).path,
            reverse("note-detail", kwargs={"pk": post.pk}),
        )
        # self.assertEqual(entry.status, "published")
        # self.assertEqual(entry.post_type, "note")

    def test_create_entry_json(self):
        content_type = "application/json"
        data = {
            "type": ["h-entry"],
            "properties": {"content": ["hello world"]},
        }

        resp = self.client.post(
            self.endpoint,
            content_type=content_type,
            data=data,
            HTTP_ACCEPT=content_type,
        )

        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.has_header("Location"))
        self.assertEqual(Post.objects.count(), 1)

        entry = Post.objects.get(id=1)

        self.assertEqual(entry.content, "hello world")
        # self.assertEqual(entry.status, "published")
        # self.assertEqual(entry.post_type, "note")

    def test_create_post_with_tags(self):
        data = {"content": "a post with some tags", "category": ("apple", "orange")}
        resp = self.client.post(self.endpoint, data)

        self.assertEqual(resp.status_code, 201)

        post = Post.objects.get(id=1)

        self.assertEqual(post.tags, "['apple', 'orange']")

    def test_create_post_with_tags_json(self):
        content_type = "application/json"
        data = {
            "type": ["h-entry"],
            "properties": {
                "content": ["hello world"],
                "category": ["apple", "orange"],
            },
        }

        resp = self.client.post(
            self.endpoint,
            content_type=content_type,
            data=data,
            HTTP_ACCEPT=content_type,
        )

        self.assertEqual(resp.status_code, 201)
        self.assertTrue(resp.has_header("Location"))
        self.assertEqual(Post.objects.count(), 1)

        post = Post.objects.get(id=1)

        self.assertEqual(post.content, "hello world")
        self.assertEqual(post.tags, "['apple', 'orange']")
        # self.assertEqual(entry.status, "published")
        # self.assertEqual(entry.post_type, "note")

    def test_update_post_action(self):
        Post.objects.create(title="first post", content="hello world")

        content_type = "application/json"
        data = {
            "action": "update",
            "url": "http://example.com/notes/1/",
            "replace": {
                "content": ["hello moon"],
            },
        }

        resp = self.client.post(
            self.endpoint,
            content_type=content_type,
            data=data,
            HTTP_ACCEPT=content_type,
        )

        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.has_header("Location"))

        post = Post.objects.get(id=1)
        self.assertEqual(post.title, "first post")
        self.assertEqual(post.content, "hello moon")
