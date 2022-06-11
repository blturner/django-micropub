from django.db import models

from model_utils.models import SoftDeletableModel


class MicropubModel(SoftDeletableModel, models.Model):
    class Meta:
        abstract = True

    @staticmethod
    def from_url(url):
        raise NotImplementedError
