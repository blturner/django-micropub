from urllib.parse import urlparse

from django.db import models
from django.urls import resolve, reverse


class Post(models.Model):
    title = models.CharField(max_length=100)
    content = models.TextField()
    tags = models.CharField(max_length=255)

    def get_absolute_url(self):
        return reverse("note-detail", kwargs={"pk": self.pk})

    @staticmethod
    def from_url(url):
        view, args, kwargs = resolve(urlparse(url).path)
        post = Post.all_objects.get(pk=kwargs.get("pk"))
        return post


class AdvancedPost(models.Model):
    title = models.CharField(max_length=100)
    slug = models.SlugField()
    content = models.TextField()

    def get_absolute_url(self):
        return reverse("advanced-note-detail", kwargs={"slug": self.slug})

    @staticmethod
    def from_url(url):
        view, args, kwargs = resolve(urlparse(url).path)
        post = AdvancedPost.objects.get(slug=kwargs.get("slug"))
        return post
