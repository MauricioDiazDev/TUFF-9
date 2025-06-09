from django.db import models
from django.conf import settings
from personas.models import Persona
from matriculas.models import Matricula

class SearchHistory(models.Model):
    USER_CHOICES = [
      ('plate_video','Placa Vídeo'),
      ('plate_image','Placa Imagen'),
      ('face_video','Rostro Vídeo'),
      ('face_image','Rostro Imagen'),
    ]
    user      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    category  = models.CharField(max_length=20, choices=USER_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    params    = models.JSONField(blank=True, null=True)  # rutas, filtros, etc.
    result_count = models.IntegerField(null=True, blank=True)
    items_count  = models.IntegerField(null=True, blank=True)

class BulkCheck(models.Model):
    """Registro de ejecución de un chequeo masivo."""
    CHECK_CHOICES = [('matricula','Matrícula'),('persona','Persona')]
    user      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    check_type= models.CharField(max_length=10, choices=CHECK_CHOICES)
    timestamp = models.DateTimeField(auto_now_add=True)
    input_file= models.FileField(upload_to='checks/%Y/%m/%d/')
    result_file = models.FileField(upload_to='checks/%Y/%m/%d/', blank=True)

class Report(models.Model):
    REPORT_CHOICES = [('summary','Resumen búsquedas'), ('stats','Estadísticas')]
    user       = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    report_type= models.CharField(max_length=20, choices=REPORT_CHOICES)
    created    = models.DateTimeField(auto_now_add=True)
    file       = models.FileField(upload_to='reports/%Y/%m/%d/')
