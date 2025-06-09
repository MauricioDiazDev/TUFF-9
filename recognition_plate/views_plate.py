import os
import uuid
import csv

from django.shortcuts import get_object_or_404
from django.contrib.auth.decorators import login_required
from celery.result import AsyncResult
from django.conf import settings
from django.shortcuts import render
from django.http import JsonResponse
from django.utils import timezone

from .forms_plate import VideoPlacaForm
from .tasks_plate import process_video_plate, process_image_plate 

from pathlib import Path
from matriculas.models import Matricula
from utilidades.models import SearchHistory

import glob

@login_required
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

        # Registrar en historial de búsquedas
        history=SearchHistory.objects.create(
            user=request.user,
            category='plate_video',
            params={'video_name': video_name},
            items_count=1
        )

        task = process_video_plate.delay(video_path, history.id)
        contexto = {'form': None, 'task_id': task.id}

    return render(request, 'recognition_plate/buscar_video_placa.html', contexto)


TMP_IMG_DIR = os.path.join(settings.MEDIA_ROOT, 'recognition_plate', 'tmp', 'imagenes')
os.makedirs(TMP_IMG_DIR, exist_ok=True)

@login_required
def reconocer_placa_imagen(request):
    """
    GET → muestra buscar_placa_imagen.html
    POST → guarda imágenes en tmp/, lanza tarea Celery y devuelve task_id para AJAX.
    """
    contexto = {'task_id': None}

    if request.method == 'POST':
        imagenes = request.FILES.getlist('imagenes')
        rutas_guardadas = []

        for imagen in imagenes:
            if not imagen.content_type.startswith('image/'):
                continue

            nombre_ext = os.path.splitext(imagen.name)[1]
            nombre_unico = f"{uuid.uuid4().hex}_{timezone.now().strftime('%Y%m%d%H%M%S')}{nombre_ext}"
            ruta_destino = os.path.join(TMP_IMG_DIR, nombre_unico)

            with open(ruta_destino, 'wb+') as f:
                for chunk in imagen.chunks():
                    f.write(chunk)

            rutas_guardadas.append(ruta_destino)

        if rutas_guardadas:

            history = SearchHistory.objects.create(
                user=request.user,
                category='plate_image',
                params={'filenames': [Path(p).name for p in rutas_guardadas]},
                items_count=len(rutas_guardadas)
            )
            task = process_image_plate.delay(rutas_guardadas, history.id)
            contexto['task_id'] = task.id

    return render(request, 'recognition_plate/buscar_placa_imagen.html', contexto)


@login_required
def verificar_estado_tarea(request, task_id):
    res = AsyncResult(str(task_id))
    if res.state == 'SUCCESS':
        return JsonResponse({'estado': 'completo'})
    elif res.state == 'FAILURE':
        return JsonResponse({'estado': 'error'})
    return JsonResponse({'estado': 'pendiente'})

@login_required
def mostrar_resultados_placas(request):
    """
    Vista que muestra los resultados después de que finaliza el reconocimiento
    por imágenes o vídeo, buscando el CSV más reciente generado.
    """

    # Directorios base
    csv_dir       = Path(settings.MEDIA_ROOT) / "recognition_plate" / "csv"
    annotated_url = settings.MEDIA_URL + "recognition_plate/annotated/"

    resultados = []
    csv_url    = None

    # 1) Encontrar el CSV más reciente en csv_dir
    pattern = str(csv_dir / "placas_*.csv")
    csv_files = glob.glob(pattern)
    if csv_files:
        # Escoge el que tenga la fecha más alta en el nombre
        latest_csv = max(csv_files, key=lambda p: Path(p).stat().st_mtime)
        # Construye la URL para descargar
        csv_url = settings.MEDIA_URL + "recognition_plate/csv/" + Path(latest_csv).name

        # 2) Leer ese CSV
        with open(latest_csv, newline="", encoding="utf-8") as f:
            lector = csv.DictReader(f)
            for fila in lector:
                plate         = fila["plate"]
                imagen_nombre = fila["imagen"]
                # La vista espera "<imagen>_anotada.jpg"
                imagen_file   = f"{Path(imagen_nombre).stem}_anotada.jpg"
                imagen_url    = annotated_url + imagen_file

                try:
                    obj = Matricula.objects.get(numero=plate)
                    registrada = True
                    id_ficha   = obj.id
                except Matricula.DoesNotExist:
                    registrada = False
                    id_ficha   = None

                resultados.append({
                    "matricula":  plate,
                    "pais":       fila["country"],
                    "confianza":  fila["confidence"],
                    "imagen":     imagen_url,
                    "registrada": registrada,
                    "id_ficha":   id_ficha
                })

    # 3) Renderizar pasando también csv_url para el botón de descarga
    return render(request, 'recognition_plate/resultados_placa.html', {
        'resultados': resultados,
        'csv_url':    csv_url
    }) 

@login_required
def ficha_policial(request, matricula_id):
    """
    Muestra la ficha policial de una matrícula concreta.
    """
    matricula = get_object_or_404(Matricula, pk=matricula_id)
    task_id = request.GET.get('task_id')
    return render(request, 'recognition_plate/ficha_policial.html', {
        'matricula': matricula,
        'task_id': task_id
    })