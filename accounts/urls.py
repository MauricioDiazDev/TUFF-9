# accounts/urls.py

from django.urls import path
from django.contrib.auth import views as auth_views

app_name = 'accounts'

urlpatterns = [
    # Ruta para mostrar formulario de login. Django buscará la plantilla
    # 'registration/login.html' (ver más abajo).
    path('login/', auth_views.LoginView.as_view(template_name='accounts/login.html'), name='login'),
    # Ruta para logout (redirige a 'login' al cerrar la sesión).
    path('logout/', auth_views.LogoutView.as_view(next_page='accounts:login'), name='logout'),
]
