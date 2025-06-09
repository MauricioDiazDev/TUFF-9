# tuffsite/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),

    # Rutas de la aplicación principal
    path('', views.index, name='index'),

    # Rutas de la aplicación principal
    path('about/', views.about, name='about'),

    # Rutas de contacto
    path('contact/', views.contact, name='contact'),

    # Rutas de la aplicación de dashboard
    path('dashboard/', include('dashboard.urls')),

    # Login/Logout en '/accounts/...'
    path('accounts/', include('accounts.urls', namespace='accounts')),

    # Reconocimiento facial en '/recognition_face/...'
    path('recognition_face/', include('recognition_face.urls', namespace='recognition_face')),

    # Reconocimiento de placas en '/recognition_plate/...'
    path('recognition_plate/', include('recognition_plate.urls', namespace='recognition_plate')),

    # Utilidades en '/utilidades/...'
    path('utilidades/', include('utilidades.urls', namespace='utilidades'))


]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
