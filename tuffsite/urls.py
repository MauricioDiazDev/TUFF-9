# tuffsite/urls.py
from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),

    # Landing page en '/' (dashboard.index)
    path('', include('dashboard.urls', namespace='dashboard')),

    # Login/Logout en '/accounts/...'
    path('accounts/', include('accounts.urls', namespace='accounts')),

    # Reconocimiento facial en '/recognition_face/...'
    path('recognition_face/', include('recognition_face.urls', namespace='recognition_face')),

    # Reconocimiento de placas en '/recognition_plate/...'
    path('recognition_plate/', include('recognition_plate.urls', namespace='recognition_plate')),

    # (Más adelante añadiremos rutas de otras apps aquí)

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
