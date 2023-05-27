from django import forms
from django.core.exceptions import ValidationError
from django.views import generic
from django.urls import path

from micropub.views import MicropubView, MediaEndpoint

from tests.models import AdvancedPost, Post


class PostForm(forms.ModelForm):
    title = forms.CharField(required=False)
    content = forms.CharField(required=False)
    tags = forms.CharField(required=False)

    class Meta:
        model = Post
        fields = "__all__"


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
