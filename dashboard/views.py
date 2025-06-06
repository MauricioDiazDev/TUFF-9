# dashboard/views.py

from django.shortcuts import render
from django.contrib.auth.decorators import login_required

def index(request):
    """
    Vista pública para la landing page en '/'.
    """
    return render(request, 'dashboard/index.html')

@login_required
def panel(request):
    """
    Vista protegida para el dashboard interno en '/dashboard/'.
    Solo usuarios autenticados pueden acceder.
    """
    return render(request, 'dashboard/panel.html')
