from django.apps import apps
from django.conf import settings
from django.conf.urls import url
from django.http import Http404, HttpResponseNotFound
from django.utils import six
from django.views import generic

from .models import Post
from .utils import get_singular, get_post_model


class PostMixin(object):
    model = get_post_model()
    post_type = None

    def get_queryset(self):
        try:
            post_type = self.kwargs.get("post_type")
            queryset = Post.published.filter(post_type=get_singular(post_type)).exclude(
                is_removed=True
            )
            # ordering = self.get_ordering()
            # if ordering:
            #     if isinstance(ordering, six.string_types):
            #         ordering = (ordering, six.string_types)
            #     queryset = queryset.order_by(*ordering)
            return queryset
        except IndexError:
            raise Http404

    def get_context_data(self, **kwargs):
        kwargs = super().get_context_data()
        kwargs.update({"post_type": self.kwargs.get("post_type")})
        return kwargs


class PostList(PostMixin, generic.ListView):
    pass


class PostDetail(PostMixin, generic.DetailView):
    def get_object(self):
        ts = int(self.kwargs.get(self.pk_url_kwarg))
        queryset = Post.published.from_timestamp(ts)

        try:
            obj = queryset.get()
        except queryset.model.DoesNotExist:
            raise Http404()

        return obj

    def get_template_names(self):
        post_type = get_singular(self.kwargs.get("post_type"))

        template_names = super().get_template_names()
        template_name = f"micropub/{post_type}_detail.html"

        return [template_name] + template_names


class SluggedPostDetail(generic.DetailView):
    model = Post

    def get_queryset(self):
        qs = super().get_queryset()

        post_type = get_singular(self.kwargs.get("post_type"))

        if not post_type in settings.MICROPUB_POST_TYPES.keys():
            raise Http404()

        return qs.filter(post_type=post_type)


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
    url(
        r"^(?P<post_type>\w+)/(?P<slug>[-\w]+)/$",
        SluggedPostDetail.as_view(),
        name="slug-post-detail",
    ),
]
