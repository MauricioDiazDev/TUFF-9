from django.contrib import admin
from .models import Matricula

@admin.register(Matricula)
class MatriculaAdmin(admin.ModelAdmin):
    list_display = ('numero', 'esta_robado', 'delitos_resumen', 'fecha_creacion', 'ultima_vez_vista')
    list_filter = ('esta_robado',)
    search_fields = ('numero', 'delitos', 'propietarios__nombre', 'propietarios__apellidos', 'propietarios__dni')
    filter_horizontal = ('propietarios',)
    autocomplete_fields = ['propietarios']
    readonly_fields = ('fecha_creacion', 'ultima_vez_vista')

    def delitos_resumen(self, obj):
        return (obj.delitos[:50] + '...') if obj.delitos and len(obj.delitos) > 50 else obj.delitos or "—"
    delitos_resumen.short_description = "Delitos"
