from django import forms

# Límites para archivos
MAX_IMAGE_FILE_SIZE = 5 * 1024 * 1024   # 5 MB
ALLOWED_IMAGE_CONTENT_TYPES = ("image/jpeg", "image/png")

MAX_VIDEO_FILE_SIZE = 50 * 1024 * 1024  # 50 MB
ALLOWED_VIDEO_CONTENT_TYPES = (
    "video/mp4",
    "video/avi",
    "video/x-msvideo",
    "video/quicktime",
)


class ImagenBusquedaForm(forms.Form):
    imagen = forms.ImageField(
        label="Imagen de rostro",
        help_text="Seleccione una foto en formato JPEG o PNG (máx. 5 MB)."
    )

    def clean_imagen(self):
        imagen = self.cleaned_data.get('imagen')
        if not imagen:
            raise forms.ValidationError("Debe subir una imagen.")

        content_type = imagen.content_type
        if content_type not in ALLOWED_IMAGE_CONTENT_TYPES:
            raise forms.ValidationError("Formato no soportado. Solo JPEG o PNG.")
        if imagen.size > MAX_IMAGE_FILE_SIZE:
            raise forms.ValidationError("Imagen demasiado grande (máx. 5 MB).")
        return imagen


class VideoBusquedaForm(forms.Form):
    video = forms.FileField(
        label="Vídeo de rostros",
        help_text="Seleccione un archivo de vídeo (MP4, AVI, MOV; máx. 50 MB)."
    )
    frame_step = forms.IntegerField(
        label="Procesar cada N fotogramas",
        initial=10,
        min_value=1,
        required=False,
        help_text="Procesar un frame de cada N para acelerar el análisis (p.ej. 10)."
    )

    def clean_video(self):
        video = self.cleaned_data.get('video')
        if not video:
            raise forms.ValidationError("Debe subir un vídeo.")
        content_type = video.content_type
        if content_type not in ALLOWED_VIDEO_CONTENT_TYPES:
            raise forms.ValidationError("Formato no soportado. Solo MP4, AVI o MOV.")
        if video.size > MAX_VIDEO_FILE_SIZE:
            raise forms.ValidationError("Vídeo demasiado grande (máx. 50 MB).")
        return video

    def clean_frame_step(self):
        frame_step = self.cleaned_data.get('frame_step')
        return frame_step if frame_step is not None else 10
