import json
import requests

from urllib.parse import parse_qs

from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.views import View
from django.views import generic
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator


KEY_MAPPING = [
    ("title", "name"),
    ("slug", "mp-slug"),
    ("slug", "post-slug"),
    ("status", "post-status"),
    ("reply_to", "in-reply-to"),
]


class JsonResponseForbidden(JsonResponse, HttpResponseForbidden):
    pass


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


def verify_authorization(request, authorization):
    resp = requests.get(
        "https://tokens.indieauth.com/token",
        headers={
            "Content-Type": "application/json",
            "Authorization": authorization,
        },
    )
    content = parse_qs(resp.content.decode("utf-8"))
    if content.get("error"):
        return HttpResponseForbidden(content.get("error_description"))

    request.session["scope"] = content.get("scope", [])

    return content


class IndieAuthMixin(object):
    def dispatch(self, request, *args, **kwargs):
        authorization = request.META.get("HTTP_AUTHORIZATION")

        if not authorization:
            return HttpResponse("Unauthorized", status=401)

        verify_authorization(request, authorization)

        return super().dispatch(request, *args, **kwargs)


class ConfigView(IndieAuthMixin, JSONResponseMixin, View):
    def get(self, request):
        syndicate_to = []
        context = {
            # "media-endpoint": self.request.build_absolute_uri(
            #     reverse("micropub-media-endpoint")
            # )
            "syndicate-to": syndicate_to
        }
        return self.render_to_json_response(context)


class SourceView(IndieAuthMixin, JSONResponseMixin, View):
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
class MicropubView(JsonableResponseMixin, generic.CreateView):
    def get(self, request, *args, **kwargs):
        query = self.request.GET.get("q")

        if not query:
            return HttpResponseBadRequest()

        if query == "config" or query == "syndicate-to":
            view = ConfigView.as_view()

        if query == "source":
            view = SourceView.as_view()

        return view(request, *args, **kwargs)

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
            if "url" in data.keys():
                url = data.get("url")
                obj = self.model.from_url(url)
        except json.decoder.JSONDecodeError:
            return obj

        return obj

    def form_valid(self, form):
        authorization = self.request.META.get("HTTP_AUTHORIZATION")

        if not authorization:
            try:
                authorization = form.data['auth_token']
            except KeyError:
                return HttpResponse("Unauthorized", status=401)

        content = verify_authorization(self.request, authorization)

        scopes = content.get('scope', [])
        if len(scopes) > 0:
            scopes = scopes[0].split(' ')

        if "create" not in scopes:
            return JsonResponseForbidden({
                "error": "insufficient_scope",
                "scope": "create",
            })

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

        try:
            data = json.loads(self.request.body)
        except json.decoder.JSONDecodeError:
            data = {}

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

        if "properties" in data.keys():
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
