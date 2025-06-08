from django.urls import path
from . import views_plate as views

app_name = 'recognition_plate'

urlpatterns = [
    # Subida y procesamiento de vídeo
    path('video/', views.reconocer_placa_video, name='reconocer_placa_video'),

    # Subida y procesamiento de imágenes
    path('imagen/', views.reconocer_placa_imagen, name='reconocer_placa_imagen'),

    # Verificación unificada del estado de tareas Celery (para vídeo e imágenes)
    path('estado/<str:task_id>/', views.verificar_estado_tarea, name='verificar_estado_tarea'),

    # Mostrar resultados de placas reconocidas
    path('resultados/', views.mostrar_resultados_placas, name='mostrar_resultados_placas'),
]