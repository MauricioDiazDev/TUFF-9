from django.contrib import admin
from django.urls import reverse
from django.utils.html import format_html
from django import forms
from django.core.exceptions import ValidationError

import hashlib
import numpy as np
from PIL import Image

from .models import Persona, Direccion, HistorialPenal, EmbeddingPersona, CentroidePersona
from .forms import PersonaForm

# Importar face_app para extraer embeddings en el admin
from recognition_face.face_analysis import face_app


@admin.register(EmbeddingPersona)
class EmbeddingPersonaAdmin(admin.ModelAdmin):
    list_display = ('persona', 'fecha_creacion', 'file_hash')
    readonly_fields = ('persona', 'embedding', 'fecha_creacion', 'file_hash')
    list_filter = ('fecha_creacion',)
    search_fields = ('persona__dni', 'persona__nombre', 'persona__apellidos')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return True

    def has_module_permission(self, request):
        return False


class EmbeddingPersonaInlineForm(forms.ModelForm):
    imagen = forms.ImageField(
        label="Imagen para Embedding",
        required=False,
        help_text="Sube una foto (JPEG/PNG). El sistema extraerá el embedding automáticamente."
    )

    class Meta:
        model = EmbeddingPersona
        fields = []

    def save(self, commit=True):
        if self.instance and self.instance.pk:
            return self.instance

        img_file = self.cleaned_data.get('imagen')
        if not img_file:
            raise ValidationError("Para crear un nuevo embedding, debes subir una imagen.")

        contenido_bytes = img_file.read()
        sha256_hash = hashlib.sha256(contenido_bytes).hexdigest()
        persona = self.instance.persona

        if EmbeddingPersona.objects.filter(persona=persona, file_hash=sha256_hash).exists():
            raise ValidationError("Ese mismo fichero ya fue procesado antes para esta persona.")

        img_file.seek(0)
        img_pil = Image.open(img_file).convert('RGB')
        arr_rgb = np.array(img_pil)

        faces = face_app.get(arr_rgb)
        if not faces:
            raise ValidationError("No se detectó ningún rostro en la imagen.")

        def area(f):
            x1, y1, x2, y2 = f.bbox
            return (x2 - x1) * (y2 - y1)

        face = max(faces, key=area)
        embedding = face.embedding.tolist()

        nuevo = EmbeddingPersona(
            persona=persona,
            embedding=embedding,
            file_hash=sha256_hash
        )
        if commit:
            nuevo.save()
        return nuevo


class EmbeddingPersonaInline(admin.TabularInline):
    model = EmbeddingPersona
    form = EmbeddingPersonaInlineForm

    readonly_fields = ('fecha_creacion',)
    fields = ('imagen', 'fecha_creacion')
    extra = 0
    can_delete = False
    verbose_name = "Embedding (sube imagen)"
    verbose_name_plural = "Embeddings"


class DireccionInline(admin.TabularInline):
    model = Direccion
    extra = 1
    fields = ('direccion', 'tipo', 'fecha_inicio', 'fecha_fin')


class HistorialPenalInline(admin.TabularInline):
    model = HistorialPenal
    extra = 1
    fields = ('delito', 'fecha_delito', 'lugar', 'sentencia', 'estado')


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    form = PersonaForm

    list_display = (
        'nombre', 'apellidos', 'dni', 'nacionalidad',
        'sexo', 'en_busca_captura'
    )
    search_fields = ('nombre', 'apellidos', 'dni')
    list_filter = ('nacionalidad', 'sexo', 'en_busca_captura')

    readonly_fields = (
        'foto_principal_preview',
        'view_embeddings_link',
    )

    fieldsets = (
        (None, {
            'fields': (
                'nombre', 'apellidos', 'alias', 'dni',
                'fecha_nacimiento', 'nacionalidad', 'sexo',
                'en_busca_captura', 'foto_principal', 'foto_principal_preview',
                'view_embeddings_link'
            )
        }),
    )

    inlines = [
        DireccionInline,
        HistorialPenalInline,
        EmbeddingPersonaInline,
    ]

    def foto_principal_preview(self, obj):
        if not obj.foto_principal:
            return "(Sin foto)"
        url = obj.foto_principal.url
        return format_html(
            '<img src="{}" style="max-width:200px; max-height:200px; '
            'object-fit:cover; border:1px solid #ccc;" />',
            url
        )
    foto_principal_preview.short_description = "Previsualización foto"

    def view_embeddings_link(self, obj):
        if not obj.pk:
            return "(Guarda la persona para ver embeddings)"
        url = (
            reverse('admin:personas_embeddingpersona_changelist')
            + f'?persona__id__exact={obj.id}'
        )
        return format_html(
            '<a href="{}" target="_blank" class="button">Ver todos los embeddings</a>',
            url
        )
    view_embeddings_link.short_description = "Embeddings"


@admin.register(CentroidePersona)
class CentroidePersonaAdmin(admin.ModelAdmin):
    list_display = ('persona', 'fecha_actualizacion')
    readonly_fields = ('persona', 'embedding_promedio', 'fecha_actualizacion')
    search_fields = ('persona__dni', 'persona__nombre', 'persona__apellidos')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        # Que no aparezca en el menú lateral
        return False
