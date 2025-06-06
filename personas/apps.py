# personas/apps.py

from django.apps import AppConfig

class PersonasConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'personas'

    def ready(self):
        # Importa el módulo de señales para que Django las cargue
        import personas.models  # allí está nuestro @receiver(post_delete)
