import os
from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone

from .forms_plate import VideoPlacaForm
from .tasks_plate import process_video_plate


def reconocer_placa_video(request):
    """
    GET → muestra el formulario de buscar_video_placa.html
    POST → guarda el vídeo, encola process_video_plate y devuelve task_id para AJAX.
    """
    form = VideoPlacaForm(request.POST or None, request.FILES or None)
    contexto = {'form': form, 'task_id': None}

    if request.method == 'POST' and form.is_valid():
        video = form.cleaned_data['video']

        videos_dir = os.path.join(settings.MEDIA_ROOT, 'recognition_plate', 'videos')
        os.makedirs(videos_dir, exist_ok=True)

        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        base, ext = os.path.splitext(video.name)
        unique_base = f"{base}_{timestamp}"
        video_name = f"{unique_base}{ext}"
        video_path = os.path.join(videos_dir, video_name)

        # Guardar vídeo en disco
        with open(video_path, 'wb+') as f:
            for chunk in video.chunks():
                f.write(chunk)

        # Encolar Celery
        task = process_video_plate.delay(video_path)
        contexto = {'form': None, 'task_id': task.id}

    return render(request, 'recognition_plate/buscar_video_placa.html', contexto)


def estado_video_placa(request, job_id):
    """
    Endpoint JSON para estado de Celery del procesamiento de vídeo.
    Devuelve URL del CSV de únicas al finalizar.
    """
    from celery.result import AsyncResult
    res = AsyncResult(job_id)
    info = res.info or {}
    data = {
        'state': res.state,
        'info': {
            'processed_frames': info.get('processed_frames', 0),
            'total_frames':     info.get('total_frames', 0),
            'csv_unicas':       ''
        }
    }
    if res.state == 'SUCCESS':
        base_url = settings.MEDIA_URL.rstrip('/')
        csv_unicas_rel = info.get('csv_unicas', '')
        data['info']['csv_unicas'] = f"{base_url}/{csv_unicas_rel}" if csv_unicas_rel else ''

    return JsonResponse(data)
