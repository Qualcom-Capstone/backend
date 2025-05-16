from django import forms

class UploadImageForm(forms.Form):
    image = forms.ImageField()

class ImageUrlForm(forms.Form):
    image_url = forms.URLField(label='이미지 URL')