from django import forms


class DeleteForm(forms.Form):
    action = forms.CharField()
    url = forms.URLField()


class FavoriteForm(forms.ModelForm):
    url = forms.URLField()


class ReplyForm(forms.ModelForm):
    content = forms.CharField()
    url = forms.URLField()


class RepostForm(forms.ModelForm):
    content = forms.CharField(required=False)
    url = forms.URLField()
