from django import forms

# Solo pedimos el vídeo; quitamos frame_step y threshold del formulario
MAX_VIDEO_FILE_SIZE = 500 * 1024 * 1024  # 500 MB
ALLOWED_VIDEO_CONTENT_TYPES = (
    "video/mp4",
    "video/avi",
    "video/x-msvideo",
    "video/quicktime",
)

class VideoPlacaForm(forms.Form):
    video = forms.FileField(
        label="Vídeo con vehículos/matrículas",
        help_text="MP4, AVI, MOV; máx. 500 MB"
    )

    def clean_video(self):
        video = self.cleaned_data.get("video")
        if not video:
            raise forms.ValidationError("Debe subir un vídeo.")

        content_type = video.content_type
        if content_type not in ALLOWED_VIDEO_CONTENT_TYPES:
            raise forms.ValidationError("Formato no soportado. Solo MP4, AVI o MOV.")

        if video.size > MAX_VIDEO_FILE_SIZE:
            raise forms.ValidationError("Vídeo demasiado grande (máx. 500 MB).")

        return video
