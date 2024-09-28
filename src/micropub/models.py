import uuid

from django.db import models
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType

from model_utils.models import (
    TimeStampedModel,
)


def upload_to(instance, filename):
    ext = filename.split(".")[1]
    return "micropub/{0}.{1}".format(uuid.uuid4(), ext)


class Media(TimeStampedModel):
    file = models.FileField(upload_to=upload_to)

    class Meta:
        verbose_name_plural = "media"

    def __str__(self):
        return self.file.url


class MediaItem(TimeStampedModel):
    media = models.ForeignKey(Media)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")


class SyndicationTarget(TimeStampedModel, models.Model):
    uid = models.URLField(max_length=2000)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name
