from django import forms
from django.core.exceptions import ValidationError

try:
    from django.forms import JSONField
except ImportError:
    from django.contrib.postgres.forms import JSONField


class AuthForm(forms.Form):
    access_token = forms.CharField(required=False)


class DeleteForm(forms.Form):
    action = forms.CharField()
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
