#personas/forms.py
from django import forms
from .models import Persona

class PersonaForm(forms.ModelForm):
    """
    Formulario para crear o editar una Persona.
    """
    class Meta:
        model = Persona
        fields = [
            'nombre', 'apellidos', 'alias', 'dni',
            'fecha_nacimiento', 'nacionalidad', 'sexo',
            'en_busca_captura', 'foto_principal'
        ]
