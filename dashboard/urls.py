# dashboard/urls.py

from django.urls import path
from . import views

app_name = 'dashboard'

urlpatterns = [
    # Ruta para la landing page en '/'
    path('', views.index, name='index'),

    # Ruta para el dashboard interno en '/dashboard/'
    path('dashboard/', views.panel, name='panel'),
]
