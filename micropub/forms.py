from django import forms
from django.core.exceptions import ValidationError


class AuthForm(forms.Form):
    access_token = forms.CharField(required=False)


class DeleteForm(forms.Form):
    action = forms.CharField()
    url = forms.URLField()

    # def clean(self):
    #     cleaned_data = super().clean()

    #     import ipdb

    #     ipdb.set_trace()


class FavoriteForm(forms.ModelForm):
    url = forms.URLField()


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
    replace = forms.JSONField(required=False)
    add = forms.JSONField(required=False)
    delete = forms.JSONField(required=False)

    def clean(self):
        cleaned_data = super().clean()

        replace = cleaned_data.get("replace")
        add = cleaned_data.get("add")
        delete = cleaned_data.get("delete")

        if not replace and not add and not delete:
            raise ValidationError("missing replace, add, or delete key")
