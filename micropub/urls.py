from django.conf import settings
from django.conf.urls import url
from django.http import Http404, HttpResponseNotFound
from django.views import generic

from .models import Post
from .utils import get_singular


class PostMixin(object):
    model = Post

    def get_queryset(self):
        try:
            post_type = self.kwargs.get("post_type")
            return Post.published.filter(post_type=get_singular(post_type))
        except IndexError:
            raise Http404

    def get_context_data(self, **kwargs):
        kwargs = super().get_context_data()
        kwargs.update({"post_type": self.kwargs.get("post_type")})
        return kwargs


class PostList(PostMixin, generic.ListView):
    pass


class PostDetail(PostMixin, generic.DetailView):
    def get_template_names(self):
        post_type = self.object.post_type
        template_name = "micropub/{}_detail.html".format(post_type)
        template_names = super().get_template_names()
        template_names = [template_name] + template_names

        return template_names


urlpatterns = [
    url(
        r"^(?P<post_type>\w+)/$",
        PostList.as_view(),
        name="post-list",
    ),
    url(
        r"^(?P<post_type>\w+)/(?P<pk>\d+)/$",
        PostDetail.as_view(),
        name="post-detail",
    ),
]
