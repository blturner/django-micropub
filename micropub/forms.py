from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

try:
    from django.forms import JSONField
except ImportError:
    from django.contrib.postgres.forms import JSONField


from blog.models import Entry


class EntryForm(forms.ModelForm):
    """
    This form should be provided by the third party model.
    Probably needs to be set in the settings config.
    Handles the translation of indieweb terms to the django model.
    Make this subclassable by consuming libraries?
    """

    name = forms.CharField()
    slug = forms.CharField(required=False)
    status = forms.CharField()

    class Meta:
        model = Entry
        fields = [
            "content",
            "slug",
        ]
        # exclude = ["slug", "status", "status_changed", "title"]

    def save(self, commit=True):
        instance = super().save(commit=False)

        title = self.cleaned_data["name"]
        status = self.cleaned_data["status"]

        instance.title = title
        instance.published_date = timezone.now()

        if status == "published":
            instance.status = instance.STATUS.live

        if commit:
            instance.save()
        return instance


class AuthForm(forms.Form):
    access_token = forms.CharField(required=False)


class DeleteForm(forms.Form):
    action = forms.CharField()
    url = forms.URLField()

    # def clean(self):
    #     cleaned_data = super().clean()

    #     import ipdb

    #     ipdb.set_trace()


class ReplyForm(forms.ModelForm):
    content = forms.CharField()
    url = forms.URLField()


class RepostForm(forms.ModelForm):
    content = forms.CharField(required=False)
    url = forms.URLField()


class UpdateForm(forms.ModelForm):
    h = forms.ChoiceField(required=False, choices=[("entry", "entry")])
    action = forms.CharField()
    url = forms.URLField()
    replace = JSONField(required=False)
    add = JSONField(required=False)
    delete = JSONField(required=False)

    def clean(self):
        cleaned_data = super().clean()

        replace = cleaned_data.get("replace")
        add = cleaned_data.get("add")
        delete = cleaned_data.get("delete")

        if not replace and not add and not delete:
            raise ValidationError("missing replace, add, or delete key")
