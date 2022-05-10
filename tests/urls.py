from django import forms
from django.views import generic
from django.urls import path

from micropub.views import MicropubView, IndieLogin, VerifyLogin, start_auth

from tests.models import AdvancedPost, Post


class PostForm(forms.ModelForm):
    title = forms.CharField(required=False)
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
        "notes/<slug:slug>/",
        generic.DetailView.as_view(model=AdvancedPost),
        name="advanced-note-detail",
    ),
    path("notes/<int:pk>/", generic.DetailView.as_view(model=Post), name="note-detail"),
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
    path("micropub/login/", start_auth, name="micropub-login"),
    path("micropub/login/verify/", VerifyLogin.as_view(), name="micropub-verify"),
]
