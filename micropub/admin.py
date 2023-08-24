from django.contrib import admin

from .models import Post, Media, Syndication


class PostAdmin(admin.ModelAdmin):
    list_display = ["__str__", "post_type"]


admin.site.register(Post, PostAdmin)
admin.site.register(Media)
admin.site.register(Syndication)
