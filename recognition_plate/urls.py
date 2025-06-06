from django.urls import path
from . import views_plate as views

app_name = 'recognition_plate'

urlpatterns = [
    # Solo quedan las rutas de vídeo y el estado de la tarea
    path('video/', views.reconocer_placa_video, name='reconocer_placa_video'),
    path('estado/<str:job_id>/', views.estado_video_placa, name='estado_video_placa'),
]
