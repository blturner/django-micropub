# -*- coding: utf-8 -*-
# Generated by Django 1.11.29 on 2023-08-28 05:54
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('micropub', '0006_remove_post_syndicate_to'),
    ]

    operations = [
        migrations.RenameField(
            model_name='post',
            old_name='syndication_targets',
            new_name='syndication_to',
        ),
    ]
