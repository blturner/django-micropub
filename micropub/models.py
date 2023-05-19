import uuid

from django.db import models

from model_utils.models import SoftDeletableModel, TimeStampedModel


def upload_to(instance, filename):
    ext = filename.split(".")[1]
    return "micropub/{0}.{1}".format(uuid.uuid4(), ext)


class Media(TimeStampedModel):
    file = models.FileField(upload_to=upload_to)

    class Meta:
        verbose_name_plural = "media"

    def __str__(self):
        return self.file.url


class MicropubModel(SoftDeletableModel, TimeStampedModel, models.Model):
    # need to move name, content, tags, url to this model
    media = models.ManyToManyField(
        Media,
        # related_name="%(app_label)s_%(class)s_related",
        # related_query_name="%(app_label)s_%(class)ss",
        blank=True,
    )

    class Meta:
        abstract = True

    @staticmethod
    def from_url(url):
        raise NotImplementedError
