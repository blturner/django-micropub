import json
import logging
import requests

from urllib.parse import parse_qs

from django import forms
from django.conf import settings
from django.core.exceptions import BadRequest
from django.forms.models import model_to_dict
from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    HttpResponseForbidden,
    JsonResponse,
)
from django.views import View
from django.views import generic
from django.views.generic.edit import ModelFormMixin
from django.views.decorators.csrf import csrf_exempt
from django.urls import reverse
from django.utils.decorators import method_decorator

from .forms import DeleteForm
from .models import Media


logger = logging.getLogger(__name__)


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

    scope = content.get("scope")

    logger.info(f"micropub scope: {scope}")

    request.session["scope"] = content.get("scope", [])

    return content


class IndieAuthMixin(object):
    def dispatch(self, request, *args, **kwargs):
        authorization = request.META.get("HTTP_AUTHORIZATION")

        if not authorization:
            return HttpResponse("Unauthorized", status=401)

        verify_authorization(request, authorization)

        return super().dispatch(request, *args, **kwargs)


class MicropubObjectMixin(object):
    def get_object(self):
        obj = None

        if self.request.content_type == "application/json":
            try:
                data = json.loads(self.request.body)
                obj = self.model.from_url(data["url"])
            except (json.decoder.JSONDecodeError, KeyError):
                raise BadRequest()
        else:
            if "url" in self.request.POST.keys():
                obj = self.model.from_url(self.request.POST["url"])
        return obj


class ConfigView(IndieAuthMixin, JSONResponseMixin, View):
    def get(self, request):
        syndicate_to = []
        context = {
            "media-endpoint": request.build_absolute_uri(
                reverse("micropub-media-endpoint")
            ),
            "syndicate-to": syndicate_to,
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


class MicropubCreateView(JsonableResponseMixin, generic.CreateView):
    def form_valid(self, form):
        self.object = form.save()

        if form.files:
            for f in form.files:
                file = form.files.get(f)
                media = Media.objects.create(file=file)
                self.object.media.add(media)
            self.object.save()

        if "photo" in form.data.keys():
            try:
                file = form.data.get("photo").split(settings.MEDIA_URL)[1]
                media = Media.objects.get(file__exact=file)
                self.object.media.add(media)
                self.object.save()
            except (Media.DoesNotExist, IndexError):
                self.object.delete()
                return JsonResponse(
                    {
                        "error": "invalid_request",
                        "error_description": "Media does not exist",
                    },
                    status=400,
                )

        resp = HttpResponse(status=201)
        resp["Location"] = self.request.build_absolute_uri(
            self.object.get_absolute_url()
        )
        return resp

    def form_invalid(self, form):
        return JsonResponse(
            {"error": "invalid_request", "error_description": form.errors},
            status=400,
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if self.request.content_type == "application/json":
            try:
                data = json.loads(self.request.body)

                if "category" in data.get("properties", {}).keys():
                    properties = data.get("properties")
                    properties["tags"] = ", ".join(properties.pop("category"))

                if "properties" in data.keys():
                    kwargs.update(
                        {
                            "data": {
                                k: v[0] if len(v) == 1 else v
                                for (k, v) in data.get(
                                    "properties", {}
                                ).items()
                            }
                        }
                    )
                    try:
                        if "html" in kwargs.get("data").get("content").keys():
                            kwargs.get("data").update(
                                {
                                    "content": kwargs.get("data")
                                    .get("content")
                                    .get("html")
                                }
                            )
                    except AttributeError:
                        pass

                    return kwargs
            except json.decoder.JSONDecodeError:
                logger.debug("bad json")
                raise BadRequest("Bad json")

        kwargs_data = kwargs.get("data", {})
        kwargs_data_copy = {}
        for key in kwargs_data.keys():
            if key in ["category", "category[]"]:
                kwargs_data_copy["category"] = kwargs_data.getlist(key)
            else:
                kwargs_data_copy[key] = kwargs_data.get(key)
        kwargs.update({"data": kwargs_data_copy})

        if "category" in kwargs.get("data", {}).keys():
            data = {}
            data.update(kwargs.get("data"))
            data["tags"] = ", ".join(data.pop("category"))
            kwargs.update({"data": data})

        return kwargs


class MicropubUpdateView(
    MicropubObjectMixin, JsonableResponseMixin, generic.UpdateView
):
    def form_valid(self, form):
        self.object = form.save()

        return HttpResponse(status=204)

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if self.object:
            model_fields = model_to_dict(self.object)
            model_fields.update({"tags": self.get_tags()})
            kwargs.update({"data": model_fields})

        if self.request.content_type == "application/json":
            data = json.loads(self.request.body)
            data_keys = data.keys()
            action = data.get("action")

            if action == "update":
                kwargs_data = kwargs.get("data")

                if "replace" in data_keys:
                    replace = data.get("replace")

                    try:
                        for k, v in replace.items():
                            if not isinstance(v, list):
                                raise BadRequest()
                            kwargs_data.update({k: v[0]})
                            kwargs.update({"data": kwargs_data})
                    except AttributeError:
                        raise BadRequest()

                if "add" in data_keys:
                    for k in data.get("add").keys():
                        model_k = k

                        if k == "category":
                            k = "tags"

                        tags = self.get_tags()
                        add_tag = data.get("add").get(model_k)

                        if tags and (tags != add_tag[0]):
                            vals = [tags] + add_tag
                            kwargs_data[k] = ", ".join(vals)
                        else:
                            kwargs_data[k] = add_tag[0]
                    kwargs.update({"data": kwargs_data})

                if "delete" in data_keys:
                    remove = data.get("delete")
                    if isinstance(remove, list):
                        remove_prop = remove[0]
                        if remove_prop == "category":
                            remove_prop = "tags"
                        kwargs_data[remove_prop] = None
                        kwargs.update({"data": kwargs_data})
                    else:
                        for k in remove.keys():
                            model_k = k
                            if k == "category":
                                k = "tags"

                            tags = self.get_tags()
                            remove_tag = remove.get(model_k)
                            tags = tags.replace(remove_tag[0], "")
                            kwargs_data[k] = tags.rsplit(",")[0]
                        kwargs.update({"data": kwargs_data})

        return kwargs

    def get_tags(self):
        return self.object.tags


class MicropubDeleteView(MicropubObjectMixin, generic.DeleteView):
    form_class = DeleteForm

    def form_valid(self, form):
        self.object.delete()
        return HttpResponse(status=204)

    def form_invalid(self, form):
        return JsonResponse(
            {"error": "invalid_request", "error_description": form.errors},
            status=400,
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if self.request.content_type == "application/json":
            data = json.loads(self.request.body)
            kwargs.update({"data": data})

        return kwargs


class MicropubUndeleteView(MicropubDeleteView):
    def form_valid(self, form):
        if self.object:
            self.object.is_removed = False
            self.object.save()
        return HttpResponse(status=204)


@method_decorator(csrf_exempt, name="dispatch")
class MicropubView(JsonableResponseMixin, ModelFormMixin, generic.View):
    update_view = MicropubUpdateView

    def get(self, request, *args, **kwargs):
        query = self.request.GET.get("q")

        if not query:
            logger.debug("bloop bleep")
            raise BadRequest()

        if query == "config" or query == "syndicate-to":
            view = ConfigView.as_view()

        if query == "source":
            view = SourceView.as_view()

        return view(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        action = "create"
        form = self.get_form()

        if "action" in form.data.keys():
            action = form.data.get("action")

        authorization = self.request.META.get("HTTP_AUTHORIZATION")
        access_token = form.data.get("access_token")

        if not authorization and not access_token:
            return HttpResponse("Unauthorized", status=401)

        if authorization and access_token:
            return HttpResponseBadRequest()

        if not authorization and access_token:
            authorization = f"Bearer {access_token}"

        content = verify_authorization(self.request, authorization)
        scopes = content.get("scope", [])
        if len(scopes) > 0:
            scopes = scopes[0].split(" ")

        if request.content_type == "application/json":
            action = json.loads(request.body).get("action", action)

        if action not in scopes:
            return JsonResponseForbidden(
                {"error": "insufficient_scope", "scope": action}
            )

        if action == "create":
            view = MicropubCreateView.as_view(
                model=self.model, form_class=self.form_class
            )

        if action == "update":
            view = self.update_view.as_view(
                model=self.model, form_class=self.form_class
            )

        if action == "delete":
            view = MicropubDeleteView.as_view(model=self.model)

        if action == "undelete":
            view = MicropubUndeleteView.as_view(model=self.model)

        return view(request, *args, **kwargs)


@method_decorator(csrf_exempt, name="dispatch")
class MediaEndpoint(generic.CreateView):
    model = Media
    fields = "__all__"

    def get(self, request, *args, **kwargs):
        query = self.request.GET.get("q")
        latest_upload = None

        if query == "last":
            try:
                latest_upload = self.model.objects.latest("created")
            except self.model.DoesNotExist:
                logger.debug("No media was found.")
                return JsonResponse({"url": None})
            return JsonResponse({"url": latest_upload.file.url})

        return HttpResponseBadRequest()

    def form_valid(self, form):
        self.object = form.save()

        resp = HttpResponse(status=201)

        resp["Location"] = self.request.build_absolute_uri(
            self.object.file.url
        )

        return resp

    def form_invalid(self, form):
        return JsonResponse(
            {"error": "invalid_request", "error_description": form.errors},
            status=400,
        )
