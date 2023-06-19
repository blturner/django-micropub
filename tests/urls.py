from django import forms
from django.core.exceptions import ValidationError
from django.views import generic
from django.urls import path

from micropub.views import MicropubView, MediaEndpoint

from tests.models import AdvancedPost, Post


class PostForm(forms.ModelForm):
    h = forms.ChoiceField(choices=[("entry", "entry")])
    title = forms.CharField(required=False)
    content = forms.CharField(required=False)
    tags = forms.CharField(required=False)

    class Meta:
        model = Post
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()
        # action = cleaned_data.get("action")
        content = cleaned_data.get("content")
        url = cleaned_data.get("url")

        if not url and not content:
            raise ValidationError(
                "content, reply-to, like-of, bookmark-of, or repost-of are required"
            )


class AdvancedPostForm(forms.ModelForm):
    class Meta:
        model = AdvancedPost
        fields = "__all__"


urlpatterns = [
    path(
        "notes/<int:pk>/",
        generic.DetailView.as_view(model=Post),
        name="note-detail",
    ),
    path(
        "notes/<slug:slug>/",
        generic.DetailView.as_view(model=AdvancedPost),
        name="advanced-note-detail",
    ),
    path(
        "micropub/",
        MicropubView.as_view(model=Post, form_class=PostForm),
        name="micropub",
    ),
    path(
        "advanced-micropub",
        MicropubView.as_view(model=AdvancedPost, form_class=AdvancedPostForm),
        name="advanced-micropub",
    ),
    path(
        "upload/",
        MediaEndpoint.as_view(),
        name="micropub-media-endpoint",
    ),
]
