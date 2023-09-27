from django.contrib import admin

from .models import Post, Media, Syndication, SyndicationTarget


class PostAdmin(admin.ModelAdmin):
    list_display = [
        "__str__",
        "status",
        "published_at",
        "created",
        "post_type",
        "is_removed",
    ]
    list_filter = ["post_type", "is_removed"]
    ordering = ("-published_at", "-created")


class SyndicationTargetAdmin(admin.ModelAdmin):
    list_display = ["__str__", "uid"]


admin.site.register(Post, PostAdmin)
admin.site.register(Media)
admin.site.register(Syndication)
admin.site.register(SyndicationTarget, SyndicationTargetAdmin)
