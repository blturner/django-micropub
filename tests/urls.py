from django import forms
from django.views import generic
from django.urls import path

from micropub.views import MicropubView

from tests.models import Post


class PostForm(forms.ModelForm):
    title = forms.CharField(required=False)
    tags = forms.CharField(required=False)

    class Meta:
        model = Post
        fields = '__all__'


urlpatterns = [
    path('notes/<int:pk>/', generic.DetailView.as_view(model=Post), name='note-detail'),
    path('micropub/', MicropubView.as_view(model=Post, form_class=PostForm), name='micropub'),
]
