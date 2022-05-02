from urllib.parse import urlparse

from django.db import models
from django.urls import resolve, reverse

from micropub.models import MicropubModel


class Post(MicropubModel, models.Model):
    title = models.CharField(max_length=100)
    content = models.TextField()
    tags = models.CharField(max_length=255)

    def get_absolute_url(self):
        return reverse('note-detail', kwargs={'pk': self.pk})

    @staticmethod
    def from_url(url):
        view, args, kwargs = resolve(urlparse(url).path)
        post = Post.objects.get(pk=kwargs.get('pk'))
        return post
