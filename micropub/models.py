import uuid

from django.db import models
from django.contrib.contenttypes.fields import (
    GenericForeignKey,
    GenericRelation,
)
from django.contrib.contenttypes.models import ContentType
from django.forms.fields import MultipleChoiceField

from model_utils import Choices
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
    rsvp = models.CharField(
        blank=True,
        max_length=255,
        choices=Choices(
            ("yes", "Yes"),
            ("no", "No"),
            ("maybe", "Maybe"),
            ("interested", "Interested"),
        ),
    )
    syndicate_to = models.CharField(
        max_length=255,
    )

    class Meta:
        abstract = True

    @staticmethod
    def from_url(url):
        raise NotImplementedError

    def syndicate(self):
        """
        This method should parse the rendered HTML using mf2py and send a
        micropub/webmention request to the syndication endpoint.
        """


class Syndication(TimeStampedModel, models.Model):
    url = models.URLField(blank=True, max_length=2000)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
