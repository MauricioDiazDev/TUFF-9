# utilidades/urls.py

from django.urls import path
from . import views

app_name = 'utilidades'

urlpatterns = [
    # Historial de búsquedas
    path('historial/', views.historial, name='historial'),

    # Estadísticas de uso (aún por implementar)
    path('estadisticas/', views.estadisticas, name='estadisticas'),

    # Generación de reportes PDF
    path('reportes/', views.reportes, name='reportes'),
    path('reportes/generar/', views.generar_reporte,  name='generar_reporte'),

    # Bulk check de listas (subida/lista y resultados)
    path('bulk-check/', views.bulk_check, name='bulk_check'),
    path('bulk-check/<int:pk>/', views.bulk_check_result, name='bulk_check_result'),

    # Endpoints para autocomplete AJAX
    path('autocomplete/personas/', views.autocomplete_personas, name='autocomplete_personas'),
    path('autocomplete/placas/',  views.autocomplete_placas,  name='autocomplete_placas'),

    # Búsqueda rápida y edición de resultados
    path('busqueda/', views.busqueda_rapida, name='busqueda_rapida'),
    path('busqueda/resultados/', views.busqueda_resultados, name='busqueda_resultados'),
    path('busqueda/persona/<int:pk>/editar/', views.PersonaEditView.as_view(), name='persona_editar'),
    path('busqueda/persona/<int:pk>/borrar/', views.PersonaDeleteView.as_view(), name='persona_borrar'),
    path('busqueda/placa/<int:pk>/editar/', views.MatriculaEditView.as_view(), name='placa_editar'),
    path('busqueda/placa/<int:pk>/borrar/', views.MatriculaDeleteView.as_view(), name='placa_borrar'),
]