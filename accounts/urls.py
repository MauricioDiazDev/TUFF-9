from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'accounts'

urlpatterns = [
    # login
    path('login/',
         auth_views.LoginView.as_view(template_name='accounts/login.html'),
         name='login'),

    # _AQUÍ_: usar tu LogoutView personalizado en lugar de auth_views.LogoutView_
    path('logout/', views.LogoutView.as_view(), name='logout'),

    # perfil
    path('profile/', views.profile_view, name='profile'),

    # gestión de usuarios
    path('admin/users/',        views.user_list,   name='user_list'),
    path('admin/users/create/', views.user_create, name='user_create'),
    path('admin/users/<int:pk>/edit/', views.user_edit, name='user_edit'),
]
