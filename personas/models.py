#personas/models.py
import os
import shutil
import numpy as np
from django.db import models
from django.utils.html import format_html
from django.core.exceptions import ValidationError
from django.conf import settings
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

def ruta_foto_principal(instance, filename):
    ext = os.path.splitext(filename)[1]
    return os.path.join("personas", instance.dni, filename)


class Persona(models.Model):
    nombre = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=150)
    alias = models.CharField(max_length=100, blank=True, null=True)
    dni = models.CharField(max_length=15, unique=True)
    fecha_nacimiento = models.DateField()
    nacionalidad = models.CharField(max_length=50)
    sexo = models.CharField(max_length=10)
    en_busca_captura = models.BooleanField(default=False, verbose_name="¿En busca y captura?")
    fecha_registro = models.DateTimeField(auto_now_add=True)

    foto_principal = models.ImageField(
        upload_to=ruta_foto_principal,
        blank=True,
        null=True,
        help_text="Sube la foto principal de esta persona (JPEG/PNG)."
    )

    def __str__(self):
        return f"{self.nombre} {self.apellidos} ({self.dni})"

    def clean(self):
        if Persona.objects.exclude(pk=self.pk).filter(dni=self.dni).exists():
            raise ValidationError({'dni': 'Ya existe otra persona con este DNI/NIE.'})

    def save(self, *args, **kwargs):
        self.full_clean()
        if self.pk:
            orig = Persona.objects.get(pk=self.pk)
            if orig.dni != self.dni:
                carpeta_antigua = os.path.join(settings.MEDIA_ROOT, "personas", orig.dni)
                carpeta_nueva = os.path.join(settings.MEDIA_ROOT, "personas", self.dni)
                if os.path.isdir(carpeta_antigua):
                    os.makedirs(carpeta_nueva, exist_ok=True)
                    for nombre in os.listdir(carpeta_antigua):
                        src = os.path.join(carpeta_antigua, nombre)
                        dst = os.path.join(carpeta_nueva, nombre)
                        try:
                            shutil.move(src, dst)
                        except Exception:
                            pass
                    try:
                        shutil.rmtree(carpeta_antigua)
                    except Exception:
                        pass
                    if orig.foto_principal:
                        nombre_archivo = os.path.basename(orig.foto_principal.name)
                        nueva_ruta_rel = os.path.join("personas", self.dni, nombre_archivo)
                        self.foto_principal.name = nueva_ruta_rel

        super().save(*args, **kwargs)

    def foto_principal_preview(self):
        if not self.foto_principal:
            return "(Sin foto)"
        url = self.foto_principal.url
        return format_html(
            '<img src="{}" style="max-width: 200px; max-height: 200px; '
            'object-fit:cover; border:1px solid #ccc;" />',
            url
        )
    foto_principal_preview.short_description = "Previsualización foto"


class Direccion(models.Model):
    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name="direcciones")
    direccion = models.TextField()
    tipo = models.CharField(max_length=20, choices=[
        ('actual', 'Actual'),
        ('anterior', 'Anterior'),
        ('otra', 'Otra'),
    ])
    fecha_inicio = models.DateField(null=True, blank=True)
    fecha_fin = models.DateField(null=True, blank=True)

    def __str__(self):
        return f"{self.direccion} ({self.tipo})"


class HistorialPenal(models.Model):
    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name="antecedentes")
    delito = models.TextField()
    fecha_delito = models.DateField()
    lugar = models.CharField(max_length=100)
    sentencia = models.TextField()
    estado = models.CharField(max_length=50, choices=[
        ('cumplida', 'Cumplida'),
        ('pendiente', 'Pendiente'),
        ('absuelto', 'Absuelto'),
    ])

    def __str__(self):
        return f"{self.delito} - {self.estado}"


class EmbeddingPersona(models.Model):
    persona = models.ForeignKey(Persona, on_delete=models.CASCADE, related_name="embeddings")
    embedding = models.JSONField()       # vector 512 floats
    fecha_creacion = models.DateTimeField(auto_now_add=True)
    file_hash = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        editable=False,
        help_text="SHA256 del fichero original para detectar duplicados exactos."
    )

    class Meta:
        verbose_name = "Embedding de Persona"
        verbose_name_plural = "Embeddings de Personas"
        unique_together = ('persona', 'fecha_creacion')

    def __str__(self):
        return f"Embedding {self.persona.dni} @ {self.fecha_creacion.strftime('%Y-%m-%d %H:%M:%S')}"


class CentroidePersona(models.Model):
    persona = models.OneToOneField(Persona, on_delete=models.CASCADE, related_name="centroide")
    embedding_promedio = models.JSONField()   # lista de 512 floats, L2-normalizados
    fecha_actualizacion = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Centroide de {self.persona.dni} @ {self.fecha_actualizacion}"


# Signals para recalcular centroide cada vez que cambie un EmbeddingPersona:
@receiver([post_save, post_delete], sender=EmbeddingPersona)
def recalcular_centroide(sender, instance, **kwargs):
    persona = instance.persona
    embs = []
    for ep in persona.embeddings.all():
        vec = np.array(ep.embedding, dtype='float32')
        norma = np.linalg.norm(vec)
        if norma > 0:
            embs.append(vec / norma)

    if embs:
        matriz = np.stack(embs, axis=0)
        centro = matriz.mean(axis=0)
        norma_centro = np.linalg.norm(centro)
        if norma_centro > 0:
            centro_norm = (centro / norma_centro).tolist()
        else:
            centro_norm = None
    else:
        centro_norm = None

    if centro_norm is not None:
        CentroidePersona.objects.update_or_create(
            persona=persona,
            defaults={'embedding_promedio': centro_norm}
        )
    else:
        CentroidePersona.objects.filter(persona=persona).delete()


# Eliminar carpeta de la persona cuando se borra la instancia:
@receiver(post_delete, sender=Persona)
def borrar_carpeta_persona(sender, instance, **kwargs):
    if instance.dni:
        carpeta = os.path.join(settings.MEDIA_ROOT, "personas", instance.dni)
        if os.path.isdir(carpeta):
            try:
                shutil.rmtree(carpeta)
            except Exception:
                pass
