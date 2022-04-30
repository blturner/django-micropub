from django.db import models
from django.urls import reverse

from micropub.models import MicropubModel


class Post(MicropubModel, models.Model):
    title = models.CharField(max_length=100)
    content = models.TextField()
    tags = models.CharField(max_length=255)

    def get_absolute_url(self):
        return reverse('note-detail', kwargs={'pk': self.pk})
