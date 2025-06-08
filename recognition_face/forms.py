from django import forms

MAX_IMAGE_FILE_SIZE = 5 * 1024 * 1024  # 5 MB
ALLOWED_IMAGE_CONTENT_TYPES = ("image/jpeg", "image/png")


from django import forms

class ImagenBusquedaForm(forms.Form):
    pass  # No se usa ningún campo aquí. El campo <input type="file"> está en el HTML.

class VideoBusquedaForm(forms.Form):
    video = forms.FileField(
        label="Archivo de vídeo",
        help_text="Formatos permitidos: MP4, AVI, MOV. Tamaño máximo: 200MB.",
        widget=forms.ClearableFileInput(attrs={
            'accept': 'video/mp4,video/x-msvideo,video/quicktime'
        })
    )

    def clean_video(self):
        video = self.cleaned_data.get('video')
        if video:
            if video.content_type not in ['video/mp4', 'video/x-msvideo', 'video/quicktime']:
                raise forms.ValidationError("Formato de vídeo no permitido.")
            if video.size > 200 * 1024 * 1024:
                raise forms.ValidationError("El archivo supera los 200MB permitidos.")
        return video
