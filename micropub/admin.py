from django.contrib import admin

from .models import Post, Media, Syndication, SyndicationTarget


class PostAdmin(admin.ModelAdmin):
    list_display = ["__str__", "post_type", "status"]


class SyndicationTargetAdmin(admin.ModelAdmin):
    list_display = ["__str__", "uid"]


admin.site.register(Post, PostAdmin)
admin.site.register(Media)
admin.site.register(Syndication)
admin.site.register(SyndicationTarget, SyndicationTargetAdmin)
