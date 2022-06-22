import uuid

from django.db import models

from model_utils.models import SoftDeletableModel


def upload_to(instance, filename):
    ext = filename.split(".")[1]
    return "micropub/{0}.{1}".format(uuid.uuid4(), ext)


class MicropubModel(SoftDeletableModel, models.Model):
    class Meta:
        abstract = True

    @staticmethod
    def from_url(url):
        raise NotImplementedError


class Media(models.Model):
    file = models.FileField(upload_to=upload_to)

    class Meta:
        verbose_name_plural = "media"

    def __str__(self):
        return self.file.url
