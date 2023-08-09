from django.conf import settings


def get_plural(post_type):
    return [
        val[1]
        for key, val in settings.MICROPUB_POST_TYPES.items()
        if val[0] == post_type
    ][-1]


def get_singular(post_type):
    return [
        val[0]
        for key, val in settings.MICROPUB_POST_TYPES.items()
        if val[1] == post_type
    ][-1]
