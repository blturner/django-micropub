# Generated by Django 4.0.4 on 2022-06-23 23:48

from django.db import migrations, models
import micropub.models


class Migration(migrations.Migration):

    dependencies = [
        ('micropub', '0005_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='media',
            options={'verbose_name_plural': 'media'},
        ),
        migrations.AlterField(
            model_name='media',
            name='file',
            field=models.FileField(upload_to=micropub.models.upload_to),
        ),
    ]
