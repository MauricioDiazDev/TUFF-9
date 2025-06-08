from django.urls import path
from . import views

app_name = 'recognition_face'

urlpatterns = [
    path('imagen/', views.buscar_imagen_view, name='buscar_imagen'),
    path('verificar_estado/<uuid:task_id>/', views.verificar_estado_tarea, name='verificar_estado'),
    path('resultados/<uuid:task_id>/', views.resultados_view, name='resultados'),
    path('ficha/<int:persona_id>/', views.ficha_policial, name='ficha_policial'),
    path('video/', views.buscar_video_view, name='buscar_video'),

]
