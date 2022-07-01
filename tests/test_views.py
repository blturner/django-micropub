import httpretty
import json

from urllib.parse import urlparse

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse

from tests.models import Post, AdvancedPost
from micropub.models import Media


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
    def test_form_encoded_access_token(self):
        httpretty.register_uri(
            httpretty.GET,
            "https://tokens.indieauth.com/token",
            body=b"me=https%3A%2F%2Fbenjaminturner.me%2F&issued_by=https%3A%2F%2Ftokens.indieauth.com%2Ftoken&client_id=https%3A%2F%2Fbenjaminturner.me&issued_at=1552542719&scope=create&nonce=203045553",
        )
        data = {
            "h": "entry",
            "content": "form encoded",
            "access_token": "123",
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
            "access_token": "123",
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
        self.assertEqual(resp.headers.get("Content-Type"), "application/json")
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
        url = reverse("micropub-media-endpoint")

        expected = {
            "media-endpoint": "http://example.com" + url,
            "syndicate-to": [],
        }

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(json.loads(resp.content), expected)

    def test_config_view_syndicate_to(self):
        resp = self.client.get(self.endpoint, {"q": "syndicate-to"})
        url = reverse("micropub-media-endpoint")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            json.loads(resp.content),
            {"media-endpoint": "http://example.com" + url, "syndicate-to": []},
        )

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

    def test_create_entry_with_photo(self):
        file = SimpleUploadedFile("photo.jpg", b"file_content")
        # resp = self.client.post(reverse("micropub-media-endpoint"), {"file": file})
        resp = self.client.post(
            self.endpoint,
            {
                "h": "entry",
                "content": "bananas",
                "file": file,
            },
        )

        self.assertEqual(resp.status_code, 201)

        post = Post.objects.get(content="bananas")

        self.assertEqual(
            urlparse(resp.get("location")).path,
            reverse("note-detail", kwargs={"pk": post.pk}),
        )
        self.assertEqual(post.media.count(), 1)

    def test_create_entry_with_photo_json(self):
        file = SimpleUploadedFile("photo.jpg", b"file_content")
        resp = self.client.post(reverse("micropub-media-endpoint"), {"file": file})

        data = {
            "type": ["h-entry"],
            "properties": {"content": ["bananas"], "photo": [resp.get("location")]},
        }

        resp = self.client.post(
            self.endpoint,
            data=data,
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 201)

        post = Post.objects.get(content="bananas")

        self.assertEqual(
            urlparse(resp.get("location")).path,
            reverse("note-detail", kwargs={"pk": post.pk}),
        )
        self.assertEqual(post.media.count(), 1)

    def test_create_entry_with_invalid_photo(self):
        resp = self.client.post(
            self.endpoint,
            {
                "h": "entry",
                "content": "bananas",
                "photo": "http://example.com/uploads/this-does-not-exist.jpg",
            },
        )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(Post.objects.count(), 0)

    def test_delete_entry(self):
        Post.objects.create(content="hello world")

        resp = self.client.post(
            self.endpoint,
            {"action": "delete", "url": "http://example.com/notes/1/"},
        )

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(Post.available_objects.count(), 0)
        self.assertEqual(Post.all_objects.count(), 1)

    def test_delete_entry_json(self):
        Post.objects.create(content="hello world")
        content_type = "application/json"
        data = {"action": "delete", "url": "http://example.com/notes/1/"}
        resp = self.client.post(
            self.endpoint,
            data=data,
            content_type=content_type,
            # HTTP_ACCEPT=content_type,
        )
        self.assertEqual(resp.status_code, 204)
        self.assertEqual(Post.available_objects.count(), 0)
        self.assertEqual(Post.all_objects.count(), 1)

    def test_delete_entry_missing_url(self):
        resp = self.client.post(
            self.endpoint,
            {"action": "delete"},
        )

        self.assertEqual(resp.status_code, 400)
        self.assertEqual(
            json.loads(resp.content),
            {
                "error": "invalid_request",
                "error_description": {"url": ["This field is required."]},
            },
        )

    def test_delete_entry_missing_url_json(self):
        # Post.objects.create(content="hello world")
        content_type = "application/json"
        data = {"action": "delete"}
        resp = self.client.post(
            self.endpoint,
            data=data,
            content_type=content_type,
            # HTTP_ACCEPT=content_type,
        )
        self.assertEqual(resp.status_code, 400)

    def test_delete_entry_missing_action(self):
        resp = self.client.post(
            self.endpoint,
            {"url": "http://example.com/notes/1/"},
        )

        self.assertEqual(resp.status_code, 400)

        # if the action key is omitted, it is assumed this is a request to
        # create a resource, so the error will be for a missing content key.
        self.assertEqual(
            json.loads(resp.content),
            {
                "error": "invalid_request",
                "error_description": {"content": ["This field is required."]},
            },
        )

    def test_undelete(self):
        post = Post.objects.create(content="hello world")
        post.delete()

        self.assertTrue(post.is_removed)

        resp = self.client.post(
            self.endpoint,
            {"action": "undelete", "url": "http://example.com/notes/1/"},
        )

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(Post.available_objects.count(), 1)
        self.assertEqual(Post.all_objects.count(), 1)
        self.assertFalse(Post.objects.get(pk=1).is_removed)

    def test_undelete_json(self):
        post = Post.objects.create(content="hello world")
        post.delete()

        self.assertTrue(post.is_removed)

        resp = self.client.post(
            self.endpoint,
            {"action": "undelete", "url": "http://example.com/notes/1/"},
            content_type="application/json",
        )

        self.assertEqual(resp.status_code, 204)
        self.assertEqual(Post.available_objects.count(), 1)
        self.assertEqual(Post.all_objects.count(), 1)
        self.assertFalse(Post.objects.get(pk=1).is_removed)

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

    def test_create_post_with_one_tag(self):
        data = {"content": "a post with some tags", "category": "apple"}
        resp = self.client.post(self.endpoint, data)

        self.assertEqual(resp.status_code, 201)

        post = Post.objects.get(id=1)

        self.assertEqual(post.tags, "apple")

    def test_create_post_with_tags(self):
        data = {
            "content": "a post with some tags",
            "category[]": ("apple", "orange"),
        }
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
        self.assertEqual(post.tags, "apple, orange")

    def test_update_post_action_json(self):
        post = Post.objects.create(
            title="first post", content="hello world", tags="test1, test2"
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

        self.assertEqual(resp.status_code, 204)
        self.assertFalse(resp.has_header("Location"))

        post = Post.objects.get(id=post.id)
        self.assertEqual(post.title, "first post")
        self.assertEqual(post.content, "hello moon")
        self.assertEqual(post.tags, "test1, test2")

    def test_invalid_update_post_action(self):
        content_type = "application/json"
        data = {
            "action": "update",
            # "url": "http://example.com/notes/1/",
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

        self.assertEqual(resp.status_code, 400)

    def test_update_post_action_insufficient_scope(self):
        httpretty.register_uri(
            httpretty.GET,
            "https://tokens.indieauth.com/token",
            body=b"me=https%3A%2F%2Fbenjaminturner.me%2F&issued_by=https%3A%2F%2Ftokens.indieauth.com%2Ftoken&client_id=https%3A%2F%2Fbenjaminturner.me&issued_at=1552542719&scope=create&nonce=203045553",
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

        expected = {
            "error": "insufficient_scope",
            "scope": "update",
        }

        self.assertEqual(resp.status_code, 403)
        self.assertEqual(json.loads(resp.content), expected)

    def test_create_entry_html_json(self):
        content_type = "application/json"
        data = {
            "type": ["h-entry"],
            "properties": {"content": [{"html": "<h1>Hello world</h1>"}]},
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

        self.assertEqual(entry.content, "<h1>Hello world</h1>")

    def test_rejects_auth_header_and_form_encoded_token(self):
        data = {
            "h": "entry",
            "content": "invalid",
            "access_token": "123",
        }
        resp = self.client.post(self.endpoint, data=data)

        self.assertEqual(resp.status_code, 400)

    def test_add_value_json(self):
        Post.objects.create(
            content="Micropub update test for adding a category. After you run the update, this post should have one category: test1.",
        )
        content_type = "application/json"
        data = {
            "action": "update",
            "url": "http://example.com/notes/1/",
            "add": {"category": ["test1"]},
        }

        self.client.post(
            self.endpoint,
            content_type=content_type,
            data=data,
            # HTTP_ACCEPT=content_type,
        )

        post = Post.objects.get(id=1)

        self.assertEqual(post.tags, "test1")

    def test_add_value_to_existing_property(self):
        """
        401: Add a value to an existing property
        https://micropub.rocks/server-tests/401
        """
        Post.objects.create(
            content="Micropub update test for adding a category. After you run the update, this post should have two categories: test1 and test2.",
            tags="test1",
        )
        content_type = "application/json"
        data = {
            "action": "update",
            "url": "http://example.com/notes/1/",
            "add": {"category": ["test2"]},
        }
        resp = self.client.post(
            self.endpoint,
            content_type=content_type,
            data=data,
            # HTTP_ACCEPT=content_type,
        )

        post = Post.objects.get(id=1)

        self.assertEqual(post.tags, "test1, test2")

    def test_add_duplicate_value_to_existing_property(self):
        """
        401: Add a value to an existing property
        https://micropub.rocks/server-tests/401
        """
        Post.objects.create(
            content="Micropub update test for adding a category. After you run the update, this post should have two categories: test1 and test2.",
            tags="test1",
        )
        content_type = "application/json"
        data = {
            "action": "update",
            "url": "http://example.com/notes/1/",
            "add": {"category": ["test1"]},
        }
        resp = self.client.post(
            self.endpoint,
            content_type=content_type,
            data=data,
            # HTTP_ACCEPT=content_type,
        )

        post = Post.objects.get(id=1)

        self.assertEqual(post.tags, "test1")

    def test_replace_content_and_add_value_to_existing_property(self):
        Post.objects.create(
            content="Micropub update test for adding a category. After you run the update, this post should have two categories: test1 and test2.",
            tags="test1",
        )
        content_type = "application/json"
        data = {
            "action": "update",
            "url": "http://example.com/notes/1/",
            "replace": {"content": ["hello world"]},
            "add": {"category": ["test2"]},
        }
        resp = self.client.post(
            self.endpoint,
            content_type=content_type,
            data=data,
            # HTTP_ACCEPT=content_type,
        )

        post = Post.objects.get(id=1)

        self.assertEqual(Post.objects.all().count(), 1)
        self.assertEqual(post.content, "hello world")
        self.assertEqual(post.tags, "test1, test2")

    def test_remove_property(self):
        Post.objects.create(
            content="This test deletes a category from the post. After you run the update, this post should have only the category test1.",
            tags="test1, test2",
        )
        content_type = "application/json"
        data = {
            "action": "update",
            "url": "http://example.com/notes/1/",
            "delete": ["category"],
        }
        resp = self.client.post(
            self.endpoint,
            content_type=content_type,
            data=data,
            # HTTP_ACCEPT=content_type,
        )

        self.assertEqual(resp.status_code, 204)

        post = Post.objects.get(id=1)

        self.assertEqual(Post.objects.all().count(), 1)
        self.assertFalse(post.tags)

    def test_remove_value_from_property(self):
        Post.objects.create(
            content="This test deletes a category from the post. After you run the update, this post should have only the category test1.",
            tags="test1, test2",
        )
        content_type = "application/json"
        data = {
            "action": "update",
            "url": "http://example.com/notes/1/",
            "delete": {"category": ["test2"]},
        }
        resp = self.client.post(
            self.endpoint,
            content_type=content_type,
            data=data,
            # HTTP_ACCEPT=content_type,
        )

        self.assertEqual(resp.status_code, 204)

        post = Post.objects.get(id=1)

        self.assertEqual(Post.objects.all().count(), 1)
        self.assertEqual(post.tags, "test1")

    def test_update_with_bad_request(self):
        Post.objects.create(
            content="This test deletes a category from the post. After you run the update, this post should have only the category test1.",
        )
        content_type = "application/json"
        data = {
            "action": "update",
            "url": "http://example.com/notes/1/",
            "replace": "This is in an invalid format, it should be wrapped in [].",
        }
        resp = self.client.post(
            self.endpoint,
            content_type=content_type,
            data=data,
            # HTTP_ACCEPT=content_type,
        )
        self.assertEqual(resp.status_code, 400)

        data = {
            "action": "update",
            "url": "http://example.com/notes/1/",
            "replace": {
                "content": "This is in an invalid format, it should be wrapped in []."
            },
        }
        resp = self.client.post(
            self.endpoint,
            content_type=content_type,
            data=data,
            # HTTP_ACCEPT=content_type,
        )
        self.assertEqual(resp.status_code, 400)
