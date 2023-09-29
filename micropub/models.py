import uuid
from datetime import datetime

from urllib.parse import urlparse

from django.db import models
from django.db.models import Q
from django.conf import settings
from django.contrib.contenttypes.fields import (
    GenericForeignKey,
    GenericRelation,
)
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import JSONField
from django.forms.fields import MultipleChoiceField
from django.urls import resolve, reverse

from model_utils import Choices
from model_utils.fields import MonitorField
from model_utils.managers import QueryManager
from model_utils.models import (
    SoftDeletableModel,
    StatusModel,
    TimeStampedModel,
)
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


class PostManager(QueryManager):
    def get_queryset(self):
        return (
            super().get_queryset().filter(status__in=["published", "updated"])
        )

    def from_timestamp(self, timestamp):
        dt = datetime.fromtimestamp(timestamp)

        created_lookup = Q(
            created__date=dt.date(),
            created__time__startswith=dt.time(),
            is_removed=False,
        )

        pub_date_lookup = Q(
            published_at__date=dt.date(),
            published_at__time__startswith=dt.time(),
            is_removed=False,
        )

        return super().get_queryset().filter(pub_date_lookup | created_lookup)


class Post(SoftDeletableModel, StatusModel, TimeStampedModel, models.Model):
    STATUS = Choices("draft", "published", "updated")
    TYPE_CHOICES = TYPES

    published_at = MonitorField(
        monitor="status",
        when=["published"],
        blank=True,
        null=True,
        default=None,
    )
    updated_at = MonitorField(
        monitor="status",
        when=["updated"],
        blank=True,
        null=True,
        default=None,
    )
    extra = JSONField(blank=True, default={})

    all_objects = models.Manager()
    published = PostManager()

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
    slug = models.SlugField(blank=True)
    syndicate_to = models.ManyToManyField("SyndicationTarget", blank=True)
    syndications = GenericRelation("Syndication")
    url = models.URLField(blank=True, max_length=2000)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.name or self.url or self.content

    def get_timestamp(self):
        try:
            timestamp = str(self.published_at.timestamp()).split(".")[0]
        except AttributeError:
            timestamp = str(self.created.timestamp()).split(".")[0]
        return timestamp

    def get_absolute_url(self):
        post_type = get_plural(self.post_type)
        kwargs = {"post_type": post_type}

        if self.slug:
            kwargs.update({"slug": self.slug})
            return reverse("slug-post-detail", kwargs=kwargs)

        kwargs.update({"pk": str(self.get_timestamp())})

        return reverse(
            "post-detail",
            kwargs=kwargs,
        )

    def get_next_post(self):
        return (
            Post.published.filter(
                post_type=self.post_type,
                status__in=[self.STATUS.published, self.STATUS.updated],
                published_at__gt=self.published_at,
            )
            .exclude(id__exact=self.id)
            .order_by("published_at")
            .first()
        )

    def get_prev_post(self):
        return (
            Post.published.filter(
                post_type=self.post_type,
                status__in=[self.STATUS.published, self.STATUS.updated],
                published_at__lt=self.published_at,
            )
            .exclude(id__exact=self.id)
            .order_by("-published_at")
            .first()
        )

    def get_slug_or_timestamp(self):
        return self.slug or self.get_timestamp()

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

            send_webmention(
                syndicate.endpoint, self.get_absolute_url(), self.url
            )


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
