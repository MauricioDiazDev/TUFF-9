from django.db import models
from personas.models import Persona

class Matricula(models.Model):
    numero = models.CharField(
        max_length=15,
        unique=True,
        help_text="Ej: 1234ABC (sin guiones ni espacios, siempre en mayúsculas)"
    )
    pais = models.CharField(
        max_length=10,
        blank=True,
        help_text="Código del país de la matrícula (ej. ES, FR...)"
    )
    esta_robado = models.BooleanField(default=False, verbose_name="¿Vehículo robado?")
    delitos = models.TextField(blank=True, help_text="Lista de delitos asociados (opcional)")
    propietarios = models.ManyToManyField(Persona, related_name="vehiculos", blank=True)
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    ultima_vez_vista = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.numero
