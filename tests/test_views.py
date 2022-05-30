import httpretty
import json

from urllib.parse import urlparse

from django.test import Client, TestCase
from django.urls import reverse

from tests.models import Post, AdvancedPost


class MicroPubUnauthorizedTestCase(TestCase):
    def setUp(self):
        self.endpoint = reverse("micropub")

    def test_unauthorized_config(self):
        resp = self.client.get(self.endpoint, {"q": "config"})

        self.assertEqual(resp.status_code, 401)

    def test_unauthorized_source(self):
        resp = self.client.get(self.endpoint, {"q": "source"})

        self.assertEqual(resp.status_code, 401)

    def test_unauthorized_post(self):
        resp = self.client.post(self.endpoint, {"h": "entry", "content": "bananas"})

        self.assertEqual(resp.status_code, 401)

    @httpretty.activate
    def test_form_encoded_auth_token(self):
        httpretty.register_uri(
            httpretty.GET,
            "https://tokens.indieauth.com/token",
            body=b"me=https%3A%2F%2Fbenjaminturner.me%2F&issued_by=https%3A%2F%2Ftokens.indieauth.com%2Ftoken&client_id=https%3A%2F%2Fbenjaminturner.me&issued_at=1552542719&scope=create&nonce=203045553",
        )
        data = {
            "h": "entry",
            "content": "form encoded",
            "auth_token": "123",
        }
        resp = self.client.post(self.endpoint, data)

        self.assertEqual(resp.status_code, 201)

    @httpretty.activate
    def test_form_encoded_auth_token_forbidden(self):
        httpretty.register_uri(
            httpretty.GET,
            "https://tokens.indieauth.com/token",
            body=b"error=unauthorized",
        )
        data = {
            "h": "entry",
            "content": "form encoded",
            "auth_token": "123",
        }
        resp = self.client.post(self.endpoint, data)

        self.assertEqual(resp.status_code, 403)

    @httpretty.activate
    def test_form_encoded_insufficient_create_scope(self):
        httpretty.register_uri(
            httpretty.GET,
            "https://tokens.indieauth.com/token",
            body=b"me=https%3A%2F%2Fbenjaminturner.me%2F&issued_by=https%3A%2F%2Ftokens.indieauth.com%2Ftoken&client_id=https%3A%2F%2Fbenjaminturner.me&issued_at=1552542719&scope=&nonce=203045553",
        )
        headers = {"HTTP_AUTHORIZATION": "Bearer 123"}
        data = {
            "h": "entry",
            "content": "form encoded",
        }
        resp = self.client.post(self.endpoint, data, **headers)

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.headers.get('Content-Type'), "application/json")
        expected = {
            "error": "insufficient_scope",
            "scope": "create",
        }
        self.assertEqual(json.loads(resp.content), expected)


@httpretty.activate
class MicroPubAuthorizedTestCase(TestCase):
    def setUp(self):
        httpretty.register_uri(
            httpretty.GET,
            "https://tokens.indieauth.com/token",
            body=b"me=https%3A%2F%2Fbenjaminturner.me%2F&issued_by=https%3A%2F%2Ftokens.indieauth.com%2Ftoken&client_id=https%3A%2F%2Fbenjaminturner.me&issued_at=1552542719&scope=create+update+delete+undelete&nonce=203045553",
        )

        headers = {"HTTP_AUTHORIZATION": "Bearer 123"}

        self.client = Client(SERVER_NAME="example.com", **headers)
        self.endpoint = reverse("micropub")
        self.advanced = reverse("advanced-micropub")

    def test_config_view(self):
        resp = self.client.get(self.endpoint, {"q": "config"})

        expected = {"syndicate-to": []}

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.content), expected)

    def test_config_view_syndicate_to(self):
        resp = self.client.get(self.endpoint, {"q": "syndicate-to"})

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.content), {"syndicate-to": []})

    def test_source_view_no_url(self):
        resp = self.client.get(self.endpoint, {"q": "source"})

        self.assertEqual(resp.status_code, 400)

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

    def test_create_advanced_post(self):
        resp = self.client.post(
            self.advanced,
            {
                "h": "entry",
                "title": "hello world",
                "content": "post body",
                "slug": "hello-world",
            },
        )

        self.assertEqual(resp.status_code, 201)

        post = AdvancedPost.objects.get(title="hello world")

        self.assertEqual(
            urlparse(resp.get("location")).path,
            reverse("advanced-note-detail", kwargs={"slug": "hello-world"}),
        )

    def test_create_post_json(self):
        content_type = "application/json"
        data = {"h": "entry", "content": "hello world"}
        resp = self.client.post(
            self.endpoint,
            data=data,
            HTTP_ACCEPT=content_type,
        )
        self.assertEqual(resp.status_code, 201)

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
        data = {"content": "a post with some tags", "category[]": ("apple", "orange")}
        resp = self.client.post(self.endpoint, data)

        self.assertEqual(resp.status_code, 201)

        post = Post.objects.get(id=1)

        self.assertEqual(post.tags, "apple, orange")

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
        post = Post.objects.create(
            title="first post",
            content="hello world"
        )

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

        post = Post.objects.get(id=post.id)
        self.assertEqual(post.title, "first post")
        self.assertEqual(post.content, "hello moon")
