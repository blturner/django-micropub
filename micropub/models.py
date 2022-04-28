from django.db import models


class MicropubModel(models.Model):
    class Meta:
        abstract = True

    @staticmethod
    def from_url(url):
        raise NotImplementedError
