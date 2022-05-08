from django.db import models
from django.contrib.auth.models import User


class MicropubModel(models.Model):
    class Meta:
        abstract = True

    @staticmethod
    def from_url(url):
        raise NotImplementedError


class IndieAuth(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    code = models.TextField(blank=True)
    state = models.CharField(blank=True, max_length=10)
