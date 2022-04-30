import json

from urllib.parse import urlparse

from django.http import (
    HttpResponse,
    HttpResponseBadRequest,
    JsonResponse,
    Http404,
)
from django.views import View
from django.shortcuts import render
from django.views import generic
from django.urls import resolve


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
        return JsonResponse(
            self.get_data(context),
            **response_kwargs
        )

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
        if self.request.accepts('text/html'):
            return response
        else:
            return JsonResponse(form.errors, status=400)

    def form_valid(self, form):
        # We make sure to call the parent's form_valid() method because
        # it might do some processing (in the case of CreateView, it will
        # call form.save() for example).
        response = super().form_valid(form)
        if self.request.accepts('text/html'):
            return response
        else:
            data = {
                'pk': self.object.pk,
            }
            return JsonResponse(data)


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


class MicropubView(JsonableResponseMixin, generic.CreateView):
    def form_valid(self, form):
        self.object = form.save()
        resp = HttpResponse(status=201)
        resp["Location"] = self.request.build_absolute_uri(
            self.object.get_absolute_url()
        )
        return resp

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()

        if 'category' in kwargs.get('data').keys():
            data = {}
            data.update(kwargs.get('data'))
            data['tags'] = data.pop('category')
            kwargs.update({'data': data})

        if self.request.accepts('text/html'):
            return kwargs

        data = json.loads(self.request.body)

        if 'category' in data.get('properties').keys():
            properties = data.get('properties')
            properties['tags'] = properties.pop('category')

        kwargs.update({
            'data': {k: v[0] if len(v) == 1 else v for (k, v) in data.get('properties').items()}
        })
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
