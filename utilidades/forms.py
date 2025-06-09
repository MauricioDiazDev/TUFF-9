# utilidades/forms.py

from django import forms
from .models import BulkCheck, Report
from personas.models import Persona
from matriculas.models import Matricula

class BulkCheckForm(forms.ModelForm):
    class Meta:
        model = BulkCheck
        fields = ['check_type', 'input_file']
        widgets = {
            'check_type': forms.Select(attrs={'class': 'form-select'}),
            'input_file': forms.ClearableFileInput(attrs={'class': 'form-control'}),
        }
        labels = {
            'check_type': 'Tipo de chequeo',
            'input_file': 'Archivo CSV de entrada',
        }


class ReporteForm(forms.Form):
    personas = forms.ModelMultipleChoiceField(
        queryset=Persona.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Seleccionar Personas"
    )
    matriculas = forms.ModelMultipleChoiceField(
        queryset=Matricula.objects.all(),
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Seleccionar Matrículas"
    )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get('personas') and not cleaned.get('matriculas'):
            raise forms.ValidationError(
                "Debes seleccionar al menos una persona o una matrícula."
            )
        return cleaned
