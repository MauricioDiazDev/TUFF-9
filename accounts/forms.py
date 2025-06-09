from django import forms
from django.contrib.auth import get_user_model
from django.utils.crypto import get_random_string

User = get_user_model()


User = get_user_model()

class AdminUserForm(forms.ModelForm):
    """
    Formulario para que el superusuario cree o edite usuarios.
    Al guardar:
      - Se genera un password aleatorio (8 caracteres).
      - Se construye email = inicial.username + "." + primer_apellido + "@tuff9.com"
    """
    first_name    = forms.CharField(label="Nombre(s)")
    last_name     = forms.CharField(label="Apellido(s)")
    is_staff      = forms.BooleanField(label="Usuario staff", required=False)
    is_superuser  = forms.BooleanField(label="Superusuario", required=False)

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'is_staff', 'is_superuser']

    def save(self, commit=True):
        user = super().save(commit=False)
        # Generar email
        inicial = user.username[0].lower()
        primer_apellido = self.cleaned_data['last_name'].split()[0].lower()
        user.email = f"{inicial}.{primer_apellido}@tuff9.com"

        # Si es creación (no tiene pk), generamos contraseña
        if not user.pk:
            raw_password = get_random_string(8)
            user.set_password(raw_password)
            # Guardamos la contraseña en el form para recuperarla luego
            self.raw_password = raw_password

        if commit:
            user.save()
        return user