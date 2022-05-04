from django import forms

from .models import IndieAuth


class LoginForm(forms.ModelForm):
    url = forms.URLField()
    client_id = forms.CharField()
    redirect_uri = forms.URLField()
    state = forms.CharField(required=False)

    class Meta:
        model = IndieAuth
        exclude = [
            "code",
        ]
