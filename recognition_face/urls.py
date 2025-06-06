from django.urls import path
from . import views

app_name = 'recognition_face'

urlpatterns = [
    # 1) Subir imagen para reconocimiento facial
    path('foto/', views.reconocer_foto_view, name='reconocer_foto'),

    # 2) Subir vídeo para reconocimiento facial
    path('video/', views.reconocer_video_view, name='reconocer_video'),

    # 3) Consultar estado de tarea Celery (JSON)
    path('estado/<str:job_id>/', views.estado_video_view, name='estado_video'),

    # 4) Mostrar ficha policial de una persona
    path('ficha/<int:persona_id>/', views.ficha_policial, name='ficha_policial'),
]
