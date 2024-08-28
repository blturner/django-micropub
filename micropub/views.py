import json
import logging
import requests

from urllib.parse import parse_qs

from django.conf import settings
from django.core.exceptions import (
    ObjectDoesNotExist,
    SuspiciousOperation,
)
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

import sentry_sdk

from sentry_sdk import capture_message

from .forms import DeleteForm
from . import forms as micropub_forms
from .models import Media, MediaItem, SyndicationTarget
from .utils import get_post_model


# from .signals import send_webmention


logger = logging.getLogger(__name__)


KEY_MAPPING = [
    ("title", "name"),
    ("slug", "mp-slug"),
    ("slug", "post-slug"),
    ("status", "post-status"),
    ("reply_to", "in-reply-to"),
]

POST_TYPES = settings.MICROPUB.get("post_types")


class BadRequest(Exception):
    """The request is malformed and cannot be processed."""

    pass


class JsonResponseForbidden(JsonResponse, HttpResponseForbidden):
    pass


class JsonResponseBadRequest(JsonResponse, HttpResponseBadRequest):
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
    # if content.get("error"):
    #     return HttpResponseForbidden(content.get("error_description"))

    scope = content.get("scope")

    logger.info(f"micropub scope: {scope}")

    request.session["scope"] = content.get("scope", [])

    return content


class IndieAuthMixin(object):
    def dispatch(self, request, *args, **kwargs):
        logger.debug(f"request: {request.body, args, kwargs}")
        authorization = request.META.get("HTTP_AUTHORIZATION")
        form = micropub_forms.AuthForm(data=self.request.POST)
        access_token = form.data.get("access_token")

        if not authorization and not access_token:
            return HttpResponse("Unauthorized", status=401)

        if authorization and access_token:
            logger.debug("has auth and token")
            # del self.request.META["HTTP_AUTHORIZATION"]
            raise SuspiciousOperation("has auth and token")
            # return HttpResponseBadRequest()

        if not authorization and access_token:
            authorization = f"Bearer {access_token}"

        if not authorization:
            return HttpResponse("Unauthorized", status=401)

        content = verify_authorization(request, authorization)
        if content.get("error"):
            return HttpResponseForbidden(content.get("error_description"))

        return super().dispatch(request, *args, **kwargs)


class MicropubObjectMixin(object):
    def get_object(self):
        obj = None

        if self.request.content_type == "application/json":
            try:
                data = json.loads(self.request.body)
                url = data.get("url")
            except (json.decoder.JSONDecodeError, KeyError):
                raise SuspiciousOperation()
        else:
            url = self.request.POST["url"]

        try:
            obj = self.model.from_url(url)
        except ObjectDoesNotExist:
            pass

        # if self.request.content_type == "application/json":
        #     try:
        #         data = json.loads(self.request.body)
        #         obj = self.model.from_url(data["url"])
        #     except (
        #         ObjectDoesNotExist,
        #         json.decoder.JSONDecodeError,
        #         KeyError,
        #     ):
        #         raise SuspiciousOperation()
        # else:
        #     if "url" in self.request.POST.keys():
        #         try:
        #             obj = self.model.from_url(self.request.POST["url"])
        #         except ObjectDoesNotExist:
        #             raise SuspiciousOperation()

        return obj


class ConfigView(IndieAuthMixin, JSONResponseMixin, View):
    def get(self, request):
        context = {
            "media-endpoint": request.build_absolute_uri(
                reverse("micropub-media-endpoint")
            ),
            "syndicate-to": list(
                SyndicationTarget.objects.values("uid", "name")
            ),
        }
        return self.render_to_json_response(context)


class SourceView(IndieAuthMixin, JSONResponseMixin, View):
    def get(self, request, **kwargs):
        properties = self.request.GET.getlist("properties[]", [])
        url = self.request.GET.get("url")

        if not url:
            return HttpResponseBadRequest()

        post = Post.from_url(url)
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


class MicropubMixin(object):
    # fields = [
    #     "name",
    #     "content",
    #     "post_type",
    #     "rsvp",
    #     "url",
    #     "status",
    #     "tags",
    # ]

    def post(self, request, *args, **kwargs):
        if not self.model:
            if request.content_type == "application/json":
                properties = json.loads(request.body.decode("utf-8")).get(
                    "properties"
                )
            else:
                properties = request.POST

            try:
                post_type = [
                    k for k in properties.keys() if k in POST_TYPES.keys()
                ][0]
            except IndexError:
                if set(["name", "content"]).issubset(properties.keys()):
                    post_type = "article"
                elif "bookmark-of" in properties.keys():
                    post_type = "bookmark"
                else:
                    post_type = "note"

            self.model = get_post_model(
                model=POST_TYPES.get(post_type).get("model")
            )

            class_string = (
                settings.MICROPUB.get("post_types")
                .get(post_type)
                .get(
                    "form_class",
                    settings.MICROPUB.get("default").get("form_class"),
                )
            )
            parts = class_string.split(".")
            mod = __import__(".".join(parts[:2]), fromlist=[parts[2]])

            self.form_class = getattr(mod, parts[2])

        return super().post(request, *args, **kwargs)

    def get_form_class(self):
        url_keys = ["like-of", "in-reply-to", "repost-of"]

        if self.request.content_type == "application/json":
            body = json.loads(self.request.body)
            properties = body.get("properties", {})

            if any(key in url_keys for key in properties.keys()):
                # self.form_class = micropub_forms.FavoriteForm
                return micropub_forms.FavoriteForm

        return super().get_form_class()


class MicropubCreateView(
    MicropubMixin, JsonableResponseMixin, generic.CreateView
):
    # form_class = micropub_forms.PostForm

    def form_valid(self, form):
        self.object = form.save()

        try:
            photos = form.files.getlist("photo")
        except AttributeError:
            photos = []

        if len(photos) > 0:
            for file in photos:
                media = Media.objects.create(file=file)
                MediaItem.objects.create(
                    content_object=self.object, media=media
                )
                # self.object.media.add(media)
            self.object.save()

        pt_keys = [k for k in form.data.keys() if k in POST_TYPES.keys()]

        for key in pt_keys:
            # self.object.post_type = post_types[key][0]

            if self.object.post_type == "rsvp":
                self.object.rsvp = form.data.get(key)
            # else:
            # setting the object.url here is skipping over URL validation
            # in the form class
            # self.object.url = form.data.get(key)

            self.object.save()

        if "photo" in form.data.keys():
            photos = form.data.get("photo")

            # this is fixing an issue in converting the data key from properties
            # below. lists of length 1 are converted to strings
            if not isinstance(photos, list):
                photos = [photos]

            for photo in photos:
                try:
                    file = photo.split(settings.MEDIA_URL)[1]
                    media = Media.objects.get(file__exact=file)
                    self.object.media.add(media)
                except (Media.DoesNotExist, IndexError):
                    self.object.delete()
                    raise SuspiciousOperation(
                        {
                            "error": "invalid_request",
                            "error_description": "Media does not exist",
                        },
                    )
            if photos:
                self.object.save()

        resp = HttpResponse(status=201)
        resp["Location"] = self.request.build_absolute_uri(
            self.object.get_absolute_url()
        )
        return resp

    def form_invalid(self, form):
        with sentry_sdk.push_scope() as scope:
            scope.set_extra("error_description", form.errors)
            capture_message("failed to create post")
        return JsonResponse(
            {"error": "invalid_request", "error_description": form.errors},
            status=400,
        )

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        url_keys = ["bookmark-of", "repost-of", "like-of", "in-reply-to"]

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

                    if kwargs.get("data").keys() >= {"name", "content"}:
                        try:
                            kwargs.get("data").update(
                                {"post_type": self.model.TYPES.article}
                            )
                        except AttributeError:
                            logger.info(
                                f"Model {self.model} does not contain TYPES attribute. Skipping post_type."
                            )
                    else:
                        kwargs.get("data").update(
                            {"post_type": self.model.TYPES.note}
                        )

                    for k in url_keys:
                        if k in kwargs.get("data").keys():
                            post_type = POST_TYPES.get(k).get("name")
                            try:
                                post_type = self.model.TYPES.__getattr__(
                                    post_type
                                )
                            except:
                                post_type = self.model.TYPE_CHOICES[post_type]

                            kwargs.get("data").update(
                                {
                                    "post_type": post_type,
                                    "url": kwargs.get("data").pop(k),
                                }
                            )

                    # if "rsvp" in kwargs.get("data").keys():
                    #     kwargs.get("data").update({
                    #         ""
                    #         })

                    if "post-status" in kwargs.get("data").keys():
                        status = kwargs.get("data").pop("post-status")

                        kwargs.get("data").update({"status": status})
                        # try:
                        #     kwargs.get("data").update(
                        #         {"status": self.model.STATUS.__getattr__(status)}
                        #     )
                        # except AttributeError:
                        #     logger.debug("Unable to publish")

                    if "mp-slug" in kwargs.get("data").keys():
                        kwargs.get("data").update(
                            {"slug": kwargs.get("data").pop("mp-slug")}
                        )

                    if "mp-syndicate-to" in kwargs.get("data").keys():
                        syndication_targets = kwargs.get("data").pop(
                            "mp-syndicate-to"
                        )

                        if not isinstance(syndication_targets, list):
                            syndication_targets = [syndication_targets]

                        syndicate_to = SyndicationTarget.objects.filter(
                            uid__in=syndication_targets
                        )

                        kwargs.get("data").update(
                            {"syndicate_to": syndicate_to}
                        )

                # bookmark-of, reply-to, like-of need to be converted to
                # the `url` key in kwargs

                if "type" in data.keys():
                    entry_type = data.get("type").pop()
                    kwargs.get("data", {}).update(
                        {"h": entry_type.replace("h-", "")}
                    )
                return kwargs
            except json.decoder.JSONDecodeError:
                logger.debug("bad json")
                raise SuspiciousOperation("Bad json")

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

        if kwargs.get("data").keys() >= {"name", "content"}:
            kwargs.get("data").update({"post_type": self.model.TYPES.article})
        else:
            kwargs.get("data").update({"post_type": self.model.TYPES.note})

        if "post-status" in kwargs.get("data", {}).keys():
            kwargs.get("data").update(
                {"status": kwargs.get("data").get("post-status")}
            )

        return kwargs


class MicropubUpdateView(
    MicropubObjectMixin,
    MicropubMixin,
    JsonableResponseMixin,
    generic.UpdateView,
):
    form_class = micropub_forms.UpdateForm

    def form_valid(self, form):
        self.object = form.save()

        return HttpResponse(status=204)

    def form_invalid(self, form):
        return super().form_invalid(form)

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

            kwargs_data = kwargs.get("data")

            # This key is not required for micropub updates, but
            # the model form requires it for the create action so
            # it's manually added here on update.
            kwargs_data.update({"h": "entry"})

            if action == "update":
                # kwargs_data = kwargs.get("data")

                if "replace" in data_keys:
                    replace = data.get("replace")

                    try:
                        for k, v in replace.items():
                            if not isinstance(v, list):
                                raise SuspiciousOperation()
                            kwargs_data.update({k: v[0]})
                            kwargs.update({"data": kwargs_data})
                    except AttributeError:
                        raise SuspiciousOperation()

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


class MicropubDeleteView(
    MicropubObjectMixin, JsonableResponseMixin, generic.DeleteView
):
    form_class = DeleteForm

    def get_object(self, url=None):
        return self.model.from_url(url=url)

    def form_valid(self, form):
        url = form.data.get("url")

        try:
            self.object = self.get_object(url=url)
        except ObjectDoesNotExist:
            msg = "The post with the requested URL was not found"
            return JsonResponseBadRequest(
                {
                    "error": "invalid_request",
                    "error_description": msg,
                },
            )

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

    def post(self, request, *args, **kwargs):
        # overridden to avoid default behavior which calls self.get_object
        form = self.get_form()
        if form.is_valid():
            return self.form_valid(form)
        else:
            return self.form_invalid(form)


class MicropubUndeleteView(MicropubDeleteView):
    def form_valid(self, form):
        url = form.data.get("url")

        try:
            self.object = self.get_object(url=url)
        except ObjectDoesNotExist:
            msg = "The post with the requested URL was not found"
            return JsonResponseBadRequest(
                {
                    "error": "invalid_request",
                    "error_description": msg,
                },
            )

        self.object.is_removed = False
        self.object.save()
        return HttpResponse(status=204)


@method_decorator(csrf_exempt, name="dispatch")
class MicropubView(
    IndieAuthMixin, JsonableResponseMixin, ModelFormMixin, generic.View
):
    # model = get_post_model()
    form_class = micropub_forms.AuthForm
    update_view = MicropubUpdateView
    # fields = "__all__"

    def get(self, request, *args, **kwargs):
        query = self.request.GET.get("q")

        if not query:
            logger.debug("bloop bleep")
            raise SuspiciousOperation()

        if query in ("config", "syndicate-to"):
            view = ConfigView.as_view()
            return view(request, *args, **kwargs)

        if query == "source":
            view = SourceView.as_view()
            return view(request, *args, **kwargs)

        return HttpResponseBadRequest()

    def post(self, request, *args, **kwargs):
        logger.debug(request.body)
        action = "create"

        if request.content_type == "application/json":
            action = json.loads(request.body).get("action", action)
        else:
            action = request.POST.get("action", action)

        # maybe this validation should be handled with a form?
        if action != "create":
            try:
                url = json.loads(request.body).get("url")
            except json.decoder.JSONDecodeError:
                url = request.POST.get("url")

            if not url:
                return JsonResponseBadRequest(
                    {
                        "error": "invalid_request",
                        "error_description": {
                            "url": ["This field is required."]
                        },
                    }
                )

        # if not h=entry this is not a create request

        view = MicropubCreateView.as_view(model=self.model)

        scopes = self.request.session.get("scope")

        if len(scopes) > 0:
            scopes = scopes[0].split(" ")

        # if no action, type, or properties this is an invalid request
        # a create post will have a type of h-entry with a properties key

        if action not in scopes:
            return JsonResponseForbidden(
                {"error": "insufficient_scope", "scope": action}
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
            return JsonResponse(
                {"url": request.build_absolute_uri(latest_upload.file.url)}
            )

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
