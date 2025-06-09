from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import get_user_model
from .forms import AdminUserForm
from django.contrib.auth.views import LogoutView as _LogoutView

User = get_user_model()

def superuser_required(view_func):
    return user_passes_test(lambda u: u.is_active and u.is_superuser)(view_func)


@login_required
def profile_view(request):
    """
    Vista para que cualquier usuario vea sus propios datos básicos y logout.
    """
    return render(request, 'accounts/profile.html')


@superuser_required
def user_list(request):
    """
    Lista de todos los usuarios (solo superusuario).
    """
    qs = User.objects.all().order_by('username')
    return render(request, 'accounts/user_list.html', {'users': qs})


@superuser_required
def user_create(request):
    """
    Creación de un nuevo usuario (solo superusuario).
    """
    if request.method == 'POST':
        form = AdminUserForm(request.POST)
        if form.is_valid():
            user = form.save()
            raw_password = getattr(form, 'raw_password', None)
            return render(request, 'accounts/user_created.html', {
                'user': user,
                'raw_password': raw_password,
            })
    else:
        form = AdminUserForm()
    return render(request, 'accounts/user_form.html', {
        'form': form,
        'creating': True
    })


@superuser_required
def user_edit(request, pk):
    """
    Edición de permisos básicos de un usuario existente.
    """
    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = AdminUserForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            return redirect('accounts:user_list')
    else:
        form = AdminUserForm(instance=user)
    return render(request, 'accounts/user_form.html', {'form': form, 'creating': False, 'user_obj': user})


class LogoutView(_LogoutView):
    # Redirige tras logout al index de dashboard
    next_page = 'index'
    # Permitir GET además de POST
    http_method_names = ['get', 'post', 'head', 'options', 'trace']

    # Opcional: si quieres que GET haga exactamente lo mismo que POST
    def get(self, request, *args, **kwargs):
        return self.post(request, *args, **kwargs)
