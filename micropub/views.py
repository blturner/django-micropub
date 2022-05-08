import json
import requests

from urllib.parse import urlparse, parse_qs, urlencode

from django.contrib.auth.mixins import LoginRequiredMixin
from django.utils.crypto import get_random_string
from django.http import (
    HttpResponse,
    HttpResponseRedirect,
    HttpResponseBadRequest,
    JsonResponse,
    Http404,
)
from django.views import View
from django.shortcuts import render
from django.views import generic
from django.views.decorators.csrf import csrf_exempt
from django.urls import resolve, reverse
from django.utils.decorators import method_decorator

from .forms import LoginForm
from .models import IndieAuth


KEY_MAPPING = [
    ("title", "name"),
    ("slug", "mp-slug"),
    ("slug", "post-slug"),
    ("status", "post-status"),
    ("reply_to", "in-reply-to"),
]


class JSONResponseMixin:
    """
    A mixin that can be used to render a JSON response.
    """

    def render_to_json_response(self, context, **response_kwargs):
        """
        Returns a JSON response, transforming 'context' to make the payload.
        """
        return JsonResponse(self.get_data(context), **response_kwargs)

    def get_data(self, context):
        """
        Returns an object that will be serialized as JSON by json.dumps().
        """
        # Note: This is *EXTREMELY* naive; in reality, you'll need
        # to do much more complex handling to ensure that arbitrary
        # objects -- such as Django model instances or querysets
        # -- can be serialized as JSON.
        return context


class JsonableResponseMixin:
    """
    Mixin to add JSON support to a form.
    Must be used with an object-based FormView (e.g. CreateView)
    """

    def form_invalid(self, form):
        response = super().form_invalid(form)
        if self.request.accepts("text/html"):
            return response
        else:
            return JsonResponse(form.errors, status=400)

    def form_valid(self, form):
        # We make sure to call the parent's form_valid() method because
        # it might do some processing (in the case of CreateView, it will
        # call form.save() for example).
        response = super().form_valid(form)
        if self.request.accepts("text/html"):
            return response
        else:
            data = {
                "pk": self.object.pk,
            }
            return JsonResponse(data)


class IndieAuthMixin(object):
    def dispatch(self, request, *args, **kwargs):
        authorization = request.META.get("HTTP_AUTHORIZATION")

        if not authorization:
            # try:
            #     indieauth = request.user.social_auth.get(provider="indieauth")
            #     authorization = "Authorization: {} {}".format(
            #         indieauth.extra_data.get("token_type"),
            #         indieauth.extra_data.get("access_token"),
            #     )
            # except UserSocialAuth.DoesNotExist:
            return HttpResponse(status=401)

        resp = requests.get(
            "https://tokens.indieauth.com/token",
            headers={
                "Content-Type": "application/json",
                "Authorization": authorization,
            },
        )
        content = parse_qs(resp.content.decode("utf-8"))

        if content.get("error"):
            return HttpResponse(content.get("error_description"), status=401)

        return super().dispatch(request, *args, **kwargs)


def start_auth(request):
    initial = {
        "client_id": "http://localhost:8000",
        "redirect_uri": request.build_absolute_uri(reverse("micropub-login")),
        "state": get_random_string(10),
        "user": request.user.id,
        "url": "http://localhost:8000",
    }
    instance, _ = IndieAuth.objects.get_or_create(user=request.user)
    form = LoginForm(request.POST or None, initial=initial, instance=instance)
    context = {"form": form}

    if form.is_valid():
        form.save()
        qs = urlencode(
            {
                "client_id": request.POST.get("client_id"),
                "redirect_uri": request.POST.get("redirect_uri"),
                "state": request.POST.get("state"),
            }
        )
        url = f"https://indieauth.com/auth?{qs}"
        return HttpResponseRedirect(url)

    return render(request, "micropub/indieauth_form.html", context)


class IndieLogin(LoginRequiredMixin, generic.CreateView):
    client_id = None
    model = IndieAuth
    form_class = LoginForm

    def get_initial(self):
        initial = super().get_initial()
        initial.update(
            {
                "client_id": self.client_id,
                "redirect_uri": self.request.build_absolute_uri(
                    reverse("micropub-login")
                ),
                "state": get_random_string(10),
                "user": self.request.user.id,
            }
        )
        return initial

    def get_success_url(self):
        qs = urlencode(
            {
                "client_id": self.request.POST.get("client_id"),
                "redirect_uri": self.request.POST.get("redirect_uri"),
                "state": self.request.POST.get("state"),
            }
        )
        url = f"https://indielogin.com/auth?{qs}"
        return url


class VerifyLogin(LoginRequiredMixin, generic.View):
    def get(self, request, *args, **kwargs):
        indie_auth = IndieAuth.objects.get(user__id=request.user.id)
        if indie_auth.state == request.GET.get("state"):
            indie_auth.code = request.GET.get("code")
            indie_auth.save()
            return HttpResponse("success")
        return HttpResponseBadRequest()


class SourceView(JSONResponseMixin, View):
    model = None

    def get(self, request, **kwargs):
        properties = self.request.GET.getlist("properties[]", [])
        url = self.request.GET.get("url")

        if not url:
            return HttpResponseBadRequest()

        post = self.model.from_url(url)
        context = {"type": ["h-entry"], "properties": {}}

        if properties:
            for prop in properties:
                if prop == "content":
                    context["properties"]["content"] = [post.content]
                if prop == "category":
                    context["properties"]["category"] = [
                        tag.name for tag in post.tags.all()
                    ]
        else:
            context["properties"]["content"] = [post.content]
            # context["properties"]["category"] = [
            #     tag.name for tag in post.tags.all()
            # ]

        return self.render_to_json_response(context)


@method_decorator(csrf_exempt, name="dispatch")
class MicropubView(JsonableResponseMixin, IndieAuthMixin, generic.CreateView):
    def post(self, request, *args, **kwargs):
        self.object = self.get_object()
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)

    def get_object(self, queryset=None):
        obj = None
        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError:
            return obj
        if "url" in data.keys():
            url = data.get("url")
            obj = self.model.from_url(url)
        return obj

    def form_valid(self, form):
        status_code = 200
        if self.object:
            self.object = form.save(commit=False)
            self.object.save(update_fields=form.data.keys())
            self.object = self.model.objects.get(pk=self.object.pk)
        else:
            self.object = form.save()
            status_code = 201
        resp = HttpResponse(status=status_code)

        if status_code == 201:
            resp["Location"] = self.request.build_absolute_uri(
                self.object.get_absolute_url()
            )
        return resp

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if "category" in kwargs.get("data", {}).keys():
            data = {}
            data.update(kwargs.get("data"))
            data["tags"] = data.pop("category")
            kwargs.update({"data": data})

        if self.request.accepts("text/html"):
            return kwargs

        data = json.loads(self.request.body)

        if "action" in data.keys():
            action = data.get("action")

            if action == "update":
                data.update(
                    {
                        "replace": json.dumps(data.get("replace", {})),
                        "add": json.dumps(data.get("add", {})),
                        "delete": json.dumps(data.get("delete", {})),
                    }
                )

                replace_data = json.loads(data.get("replace"))
                kwargs.update(
                    {
                        "data": {
                            k: v[0] if len(v) == 1 else v
                            for (k, v) in replace_data.items()
                        }
                    }
                )
                return kwargs

        if "category" in data.get("properties", {}).keys():
            properties = data.get("properties")
            properties["tags"] = properties.pop("category")

        kwargs.update(
            {
                "data": {
                    k: v[0] if len(v) == 1 else v
                    for (k, v) in data.get("properties", {}).items()
                }
            }
        )
        return kwargs


# class MicropubView(generic.FormView):
#     model = None

#     def get(self, request, *args, **kwargs):
#         query = self.request.GET.get("q")

#         if not query:
#             return HttpResponseBadRequest()

#         if query == "config":
#             view = ConfigView.as_view()

#         if query == "source":
#             view = SourceView.as_view(model=self.model)

#         return view(request, *args, **kwargs)

#     def post(self, request, *args, **kwargs):
#         embed_file = None
#         embed_alt_text = None

#         if request.content_type == "application/json":
#             data = json.loads(request.body)
#             action = data.get("action")

#             if action == "update":
#                 data.update(
#                     {
#                         "replace": json.dumps(data.get("replace", {})),
#                         "add": json.dumps(data.get("add", {})),
#                         "delete": json.dumps(data.get("delete", {})),
#                     }
#                 )

#                 post_data = request.POST.copy()
#                 post_data.update(data)
#                 request.POST = post_data

#                 return PostUpdateView.as_view()(request, *args, **kwargs)

#             if action == "delete" or action == "undelete":
#                 post_data = request.POST.copy()
#                 post_data.update(data)
#                 request.POST = post_data

#             fields = {}
#             keys = []

#             if "properties" in data.keys():
#                 keys = data["properties"].keys()

#             if "name" in keys:
#                 fields["title"] = data["properties"]["name"][0]

#             if "post-status" in keys:
#                 fields["status"] = data["properties"]["post-status"][0]

#             if "mp-slug" in keys:
#                 fields["slug"] = data["properties"]["mp-slug"][0]

#             if "content" in keys:
#                 content = data["properties"]["content"][0]

#                 if type(content) == dict and content.get("html"):
#                     fields["content"] = content["html"]
#                 else:
#                     fields["content"] = content

#             if "photo" in keys:
#                 photo = data["properties"]["photo"][0]

#                 if type(photo) == dict:
#                     embed_alt_text = photo.get("alt")
#                     embed_file = photo.get("value")
#                 else:
#                     embed_file = photo

#             if "category" in keys:
#                 fields["tags"] = " ".join(data["properties"]["category"])

#             if "in-reply-to" in keys:
#                 fields["reply_to"] = data["properties"]["in-reply-to"][0]

#         action = request.POST.get("action")

#         if action == "delete" or action == "undelete":
#             return DeleteView.as_view()(request, *args, **kwargs)

#         form = self.form_class(request.POST or fields)

#         if form.is_valid():
#             instance = form.save(commit=False)

#             for pair in KEY_MAPPING:
#                 val = request.POST.get(pair[1])
#                 if val:
#                     instance.__dict__[pair[0]] = val

#             if instance.title:
#                 instance.post_type = "post"

#             media_url = embed_file or self.request.POST.get("photo")

#             instance.save()

#             # if media_url:
#             #     parsed = urlparse(media_url)
#             #     file_name = parsed.path.split("/")[-1]
#             #     media = Media.objects.get(file__contains=file_name)

#             #     Post.media.add(media)

#             # make sure tags are saved
#             form.save_m2m()

#             resp = HttpResponse(status=201)
#             resp["Location"] = request.build_absolute_uri(
#                 instance.get_absolute_url()
#             )
#             return resp
#         return HttpResponseBadRequest()
