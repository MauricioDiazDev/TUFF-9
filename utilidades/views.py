# utilidades/views.py

import os
from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic.edit import UpdateView, DeleteView
from django.utils.decorators import method_decorator
from django.contrib.auth.decorators import login_required,permission_required
from django.urls import reverse_lazy
from django.conf import settings
from django.db.models import Count
from .models import SearchHistory, BulkCheck, Report
from .forms import BulkCheckForm, ReporteForm
from .tasks import bulk_check_task
from .utils import generar_pdf_reportes
from personas.models import Persona
from matriculas.models import Matricula
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json


@login_required
def historial(request):
    """
    Muestra el historial de búsquedas del usuario, ordenado por fecha.
    """
    qs = SearchHistory.objects.filter(user=request.user).order_by('-timestamp')
    return render(request, 'utilidades/historial.html', {'history': qs})


@login_required
def estadisticas(request):
    """
    Calcula estadísticas básicas (conteo de búsquedas por categoría y por día)
    y las pasa al template para graficar.
    """
    # Conteo por categoría
    by_cat = (
        SearchHistory.objects
        .filter(user=request.user)
        .values('category')
        .annotate(count=Count('id'))
    )
    # Conteo por día
    by_day = (
        SearchHistory.objects
        .filter(user=request.user)
        .extra({'day': "DATE(timestamp)"})
        .values('day')
        .annotate(count=Count('id'))
        .order_by('day')
    )
    return render(request, 'utilidades/estadisticas.html', {
        'by_cat': list(by_cat),
        'by_day': list(by_day),
    })


@login_required
def reportes(request):
    pdf_url = None

    if request.method == 'POST':
        form = ReporteForm(request.POST)
        if form.is_valid():
            personas   = form.cleaned_data['personas']
            matriculas = form.cleaned_data['matriculas']
            ruta_rel = generar_pdf_reportes(personas, matriculas)
            pdf_url = settings.MEDIA_URL + ruta_rel
    else:
        form = ReporteForm()

    return render(request, 'utilidades/reportes.html', {
        'form': form,
        'pdf_url': pdf_url
    })

@login_required
@require_POST
def generar_reporte(request):
    """
    Recibe JSON con listas 'persons' y 'plates', genera el PDF y devuelve
    {'pdf_url': <url_del_pdf>}
    """
    try:
        payload = json.loads(request.body)
        person_ids   = payload.get('persons', [])
        plate_ids    = payload.get('plates', [])
        personas_qs  = Persona.objects.filter(id__in=person_ids)
        matriculas_qs= Matricula.objects.filter(id__in=plate_ids)

        ruta_rel = generar_pdf_reportes(personas_qs, matriculas_qs)
        pdf_url  = settings.MEDIA_URL + ruta_rel
        return JsonResponse({'pdf_url': pdf_url})
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def bulk_check(request):
    """
    Form para subir un CSV de matrículas o personas y realizar el chequeo masivo.
    """
    if request.method == 'POST':
        form = BulkCheckForm(request.POST, request.FILES)
        if form.is_valid():
            bc = BulkCheck.objects.create(
                user=request.user,
                check_type=form.cleaned_data['check_type'],
                input_file=form.cleaned_data['input_file']
            )
            bulk_check_task.delay(bc.id)
            return redirect('utilidades:bulk_check_result', bc.id)
    else:
        form = BulkCheckForm()
    return render(request, 'utilidades/bulk_check.html', {'form': form})


@login_required
def bulk_check_result(request, pk):
    """
    Muestra los enlaces al fichero de entrada y al resultado generado.
    """
    bc = get_object_or_404(BulkCheck, pk=pk, user=request.user)
    return render(request, 'utilidades/bulk_check_result.html', {'bulkcheck': bc})

@login_required
def autocomplete_personas(request):
    q = request.GET.get("q", "").strip().upper()
    items = []
    if q:
        qs = Persona.objects.filter(dni__startswith=q)[:10]
        for p in qs:
            items.append({
                "id": p.id,
                "display": f"{p.nombre} {p.apellidos} ({p.dni})"
            })
    return JsonResponse({"results": items})

@login_required
def autocomplete_placas(request):
    q = request.GET.get("q", "").strip().upper()
    items = []
    if q:
        qs = Matricula.objects.filter(numero__startswith=q)[:10]
        for m in qs:
            items.append({
                "id": m.id,
                "display": m.numero
            })
    return JsonResponse({"results": items})

@login_required
def busqueda_rapida(request):
    return render(request, 'utilidades/busqueda.html')

@login_required
def busqueda_resultados(request):
    q = request.GET.get('q','').strip().upper()
    persona = Persona.objects.filter(dni__iexact=q).first()
    placa   = Matricula.objects.filter(numero__iexact=q).first()
    return render(request, 'utilidades/busqueda_resultados.html',{
        'persona': persona, 'placa': placa
    })

class PersonaEditView(UpdateView):
    model = Persona
    fields = ['nombre','apellidos','alias','fecha_nacimiento','nacionalidad','sexo','en_busca_captura']
    template_name = 'utilidades/persona_form.html'
    success_url = reverse_lazy('utilidades:busqueda_rapida')

    @method_decorator(permission_required('personas.change_persona', raise_exception=True))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

class PersonaDeleteView(DeleteView):
    model = Persona
    template_name = 'utilidades/confirm_delete.html'
    success_url = reverse_lazy('utilidades:busqueda_rapida')

    @method_decorator(permission_required('personas.delete_persona', raise_exception=True))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

class MatriculaEditView(UpdateView):
    model = Matricula
    fields = ['esta_robado','delitos','propietarios']
    template_name = 'utilidades/placa_form.html'
    success_url = reverse_lazy('utilidades:busqueda_rapida')

    @method_decorator(permission_required('matriculas.change_matricula', raise_exception=True))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)

class MatriculaDeleteView(DeleteView):
    model = Matricula
    template_name = 'utilidades/confirm_delete.html'
    success_url = reverse_lazy('utilidades:busqueda_rapida')

    @method_decorator(permission_required('matriculas.delete_matricula', raise_exception=True))
    def dispatch(self, *args, **kwargs):
        return super().dispatch(*args, **kwargs)