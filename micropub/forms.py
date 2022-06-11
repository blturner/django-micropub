from django import forms


class DeleteForm(forms.Form):
    action = forms.CharField()
    url = forms.URLField()
