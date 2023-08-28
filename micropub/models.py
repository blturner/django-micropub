import uuid

from urllib.parse import urlparse

from django.db import models
from django.conf import settings
from django.contrib.contenttypes.fields import (
    GenericForeignKey,
    GenericRelation,
)
from django.contrib.contenttypes.models import ContentType
from django.forms.fields import MultipleChoiceField
from django.urls import resolve, reverse

from model_utils import Choices
from model_utils.models import SoftDeletableModel, StatusModel, TimeStampedModel
from multiselectfield import MultiSelectField

from .utils import get_plural


TYPES = Choices(*[t[0] for t in settings.MICROPUB_POST_TYPES.values()])


def upload_to(instance, filename):
    ext = filename.split(".")[1]
    return "micropub/{0}.{1}".format(uuid.uuid4(), ext)


class Media(TimeStampedModel):
    file = models.FileField(upload_to=upload_to)

    class Meta:
        verbose_name_plural = "media"

    def __str__(self):
        return self.file.url


class Post(SoftDeletableModel, StatusModel, TimeStampedModel, models.Model):
    STATUS = Choices("draft", "published")
    SYNDICATION_CHOICES = Choices(
        (0, "https://archive.org/", "Internet Archive"),
        (1, "https://social.benjaminturner.me", "Mastodon"),
    )
    TYPE_CHOICES = TYPES

    name = models.CharField(blank=True, max_length=255)
    content = models.TextField(blank=True)
    post_type = models.CharField(
        choices=TYPE_CHOICES, default=TYPE_CHOICES.note, max_length=20
    )
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
    syndicate_to = models.ManyToManyField("SyndicationTarget")
    syndications = GenericRelation("Syndication")
    url = models.URLField(blank=True, max_length=2000)

    def __str__(self):
        return self.name or self.url or self.content

    def get_absolute_url(self):
        post_type = get_plural(self.post_type)
        return reverse("post-detail", kwargs={"post_type": post_type, "pk": self.pk})

    @staticmethod
    def from_url(url):
        view, args, kwargs = resolve(urlparse(url)[2])
        note = Post.objects.get(pk=kwargs.get("pk"))
        return note

    def syndicate(self, resend=False):
        """
        This method should parse the rendered HTML using mf2py and send a
        micropub/webmention request to the syndication endpoint.
        """
        for syndicate in self.syndicate_to:
            existing_syndications = Syndication.objects.filter(url=self.url)

            if existing_syndications and not resend:
                return

            send_webmention(syndicate.endpoint, self.get_absolute_url(), self.url)


class SyndicationTarget(TimeStampedModel, models.Model):
    uid = models.URLField(max_length=2000)
    name = models.CharField(max_length=255)

    def __str__(self):
        return self.name


class Syndication(TimeStampedModel, models.Model):
    url = models.URLField(blank=True, max_length=2000)
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey("content_type", "object_id")
