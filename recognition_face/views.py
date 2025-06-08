import os
from django.shortcuts import render
from django.conf import settings
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse

from .forms import ImagenBusquedaForm
from .tasks_imagenes import procesar_imagenes_task
from personas.models import Persona
from celery.result import AsyncResult


@login_required
def buscar_imagen_view(request):
    if request.method == 'GET':
        return render(request, 'recognition_face/buscar_imagen.html')

    imagenes = request.FILES.getlist('imagenes')
    errores = []
    imagenes_validas = []

    for img in imagenes:
        if img.content_type not in ("image/jpeg", "image/png"):
            errores.append(f"{img.name}: formato no permitido.")
        elif img.size > 5 * 1024 * 1024:
            errores.append(f"{img.name}: archivo demasiado grande (> 5MB).")
        else:
            imagenes_validas.append(img)

    if not imagenes_validas:
        errores.append("Debe subir al menos una imagen válida.")

    if errores:
        return render(request, 'recognition_face/buscar_imagen.html', {
            'errores': errores
        })

    tmp_dir = os.path.join(settings.MEDIA_ROOT, 'recognition_face', 'tmp')
    os.makedirs(tmp_dir, exist_ok=True)

    saved_paths = []
    for img in imagenes_validas:
        timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
        nombre = f"{timestamp}_{img.name}"
        ruta = os.path.join(tmp_dir, nombre)

        with open(ruta, 'wb+') as f:
            for chunk in img.chunks():
                f.write(chunk)

        saved_paths.append(ruta)

    task = procesar_imagenes_task.delay(saved_paths)

    return render(request, 'recognition_face/buscar_imagen.html', {
        'task_id': task.id
    })


@login_required
def verificar_estado_tarea(request, task_id):
    res = AsyncResult(str(task_id))
    if res.state == 'SUCCESS':
        return JsonResponse({'estado': 'completo'})
    elif res.state == 'FAILURE':
        return JsonResponse({'estado': 'error'})
    return JsonResponse({'estado': 'pendiente'})


@login_required
def resultados_view(request, task_id):
    res = AsyncResult(str(task_id))
    if res.state != 'SUCCESS':
        return render(request, 'recognition_face/buscar_imagen.html', {'task_id': task_id})

    info = res.result or {}
    base = settings.MEDIA_URL.rstrip('/')
    csv_url = f"{base}/{info['csv_path']}" if info.get('csv_path') else ''

    return render(request, 'recognition_face/resultados.html', {
        'descripcion': info.get('descripcion', ''),
        'csv_url': csv_url,
        'resultados': info['resultados'],
        'task_id': task_id
    })

from django.shortcuts import get_object_or_404

@login_required
def ficha_policial(request, persona_id):
    persona = get_object_or_404(Persona, pk=persona_id)
    task_id=request.GET.get('task_id')
    return render(request, 'recognition_face/ficha_policial.html', {
        'persona': persona,
        'task_id': task_id
        })

from .forms import VideoBusquedaForm
from .tasks_video import procesar_video_task


@login_required
def buscar_video_view(request):
    if request.method == 'GET':
        form = VideoBusquedaForm()
        return render(request, 'recognition_face/buscar_video.html', {'form': form})

    form = VideoBusquedaForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, 'recognition_face/buscar_video.html', {'form': form})

    video = form.cleaned_data['video']

    tmp_dir = os.path.join(settings.MEDIA_ROOT, 'recognition_face', 'tmp')
    os.makedirs(tmp_dir, exist_ok=True)

    timestamp = timezone.now().strftime('%Y%m%d_%H%M%S')
    nombre = f"video_{timestamp}.mp4"
    ruta = os.path.join(tmp_dir, nombre)

    with open(ruta, 'wb+') as f:
        for chunk in video.chunks():
            f.write(chunk)

    task = procesar_video_task.delay(ruta)

    return render(request, 'recognition_face/buscar_video.html', {
        'form': form,
        'task_id': task.id
    })