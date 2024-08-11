from django.contrib import admin

from .models import Media, SyndicationTarget


class SyndicationTargetAdmin(admin.ModelAdmin):
    list_display = ["__str__", "uid"]


admin.site.register(Media)
admin.site.register(SyndicationTarget, SyndicationTargetAdmin)
