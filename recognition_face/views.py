import os
import csv
import cv2
import numpy as np
from django.conf import settings
from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse
from django.utils import timezone
from django.contrib.auth.decorators import login_required
from PIL import Image

from .forms import ImagenBusquedaForm, VideoBusquedaForm
from .face_analysis import get_face_box, get_embedding, detect_all_faces
from .vector_index import search
from .tasks import process_video
from personas.models import Persona

# Umbral fijo de similitud (coseno) para decidir “mismo rostro”
UMBRAL_CONFIANZA = 0.65


@login_required
def reconocer_foto_view(request):
    """
    - GET  → muestra form para subir imagen
    - POST → procesa la imagen, detecta caras, busca coincidencias,
             anota la imagen, escribe CSV y renderiza resultados
    """
    if request.method == 'GET':
        form = ImagenBusquedaForm()
        return render(request, 'recognition_face/buscar.html', {'form': form})

    form = ImagenBusquedaForm(request.POST, request.FILES)
    if not form.is_valid():
        return render(request, 'recognition_face/buscar.html', {'form': form})

    # 1) Leer imagen y convertir a RGB/BGR
    uploaded = form.cleaned_data['imagen']
    img_pil = Image.open(uploaded).convert('RGB')
    arr_rgb = np.array(img_pil)
    arr_bgr = cv2.cvtColor(arr_rgb, cv2.COLOR_RGB2BGR)

    # 2) Detectar todas las caras
    detecciones = detect_all_faces(arr_rgb)
    if not detecciones:
        form.add_error(None, "No se detectó ningún rostro en la imagen.")
        return render(request, 'recognition_face/buscar.html', {'form': form})

    # 3) Preparar carpetas
    img_dir = os.path.join(settings.MEDIA_ROOT, 'recognition_face', 'imagenes')
    csv_dir = os.path.join(settings.MEDIA_ROOT, 'recognition_face', 'csv')
    os.makedirs(img_dir, exist_ok=True)
    os.makedirs(csv_dir, exist_ok=True)

    # 4) Nombre base único
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    base, _ = os.path.splitext(os.path.basename(uploaded.name))
    unique_base = f"{base}_{timestamp}"

    # 5) Rutas de salida
    csv_path = os.path.join(csv_dir, f"{unique_base}_resultados.csv")
    annotated_filename = f"{unique_base}_annotated.jpg"
    annotated_path = os.path.join(img_dir, annotated_filename)

    # 6) Copiar imagen para anotar
    annotated_img = arr_bgr.copy()
    matches_list = []

    # 7) Abrir CSV y escribir encabezado, además anotar imagen
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['persona_id', 'dni', 'nombre', 'score', 'x1', 'y1', 'x2', 'y2'])

        for (x1, y1, x2, y2), embedding, _ in detecciones:
            vecinos = search(embedding)
            if not vecinos:
                continue

            sim, pid = vecinos[0]
            if sim < UMBRAL_CONFIANZA:
                continue

            persona = Persona.objects.filter(pk=pid).first()
            if not persona:
                continue

            writer.writerow([
                pid,
                persona.dni,
                f"{persona.nombre} {persona.apellidos}",
                f"{sim:.4f}",
                x1, y1, x2, y2
            ])

            cv2.rectangle(annotated_img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            texto = f"{persona.nombre} ({sim:.2f})"
            cv2.putText(
                annotated_img,
                texto,
                (x1, y1 - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.8,
                (0, 255, 0),
                2
            )

            matches_list.append({
                'id': pid,
                'dni': persona.dni,
                'nombre': f"{persona.nombre} {persona.apellidos}",
                'score': sim,
            })

    # 8) Guardar imagen anotada
    cv2.imwrite(annotated_path, annotated_img)

    # 9) Construir URLs (MEDIA_URL)
    base_media = settings.MEDIA_URL.rstrip('/')
    annotated_url = f"{base_media}/recognition_face/imagenes/{annotated_filename}"
    csv_url = f"{base_media}/recognition_face/csv/{os.path.basename(csv_path)}"

    contexto = {
        'annotated_image_url': annotated_url,
        'csv_url': csv_url,
        'matches': matches_list,
    }
    return render(request, 'recognition_face/resultados.html', contexto)


@login_required
def reconocer_video_view(request):
    """
    - GET  → muestra form para subir vídeo
    - POST → valida, guarda vídeo, encola tarea Celery y devuelve task_id
    """
    form = VideoBusquedaForm(request.POST or None, request.FILES or None)
    contexto = {'form': form, 'task_id': None}

    if request.method == 'POST' and form.is_valid():
        video = form.cleaned_data['video']
        frame_step = form.cleaned_data['frame_step']

        # Guardar vídeo en MEDIA_ROOT/recognition_face/videos/
        videos_dir = os.path.join(settings.MEDIA_ROOT, 'recognition_face', 'videos')
        os.makedirs(videos_dir, exist_ok=True)

        timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
        base, ext = os.path.splitext(os.path.basename(video.name))
        unique_base = f"{base}_{timestamp}"
        video_filename = f"{unique_base}{ext}"
        video_path = os.path.join(videos_dir, video_filename)

        with open(video_path, 'wb+') as f:
            for chunk in video.chunks():
                f.write(chunk)

        # Encolar tarea Celery
        task = process_video.delay(video_path, frame_step)
        contexto = {'form': None, 'task_id': task.id}

    return render(request, 'recognition_face/buscar_video.html', contexto)


@login_required
def estado_video_view(request, job_id):
    """
    Endpoint JSON para consultar estado de la tarea Celery:
      - PENDING/PROGRESS → { state, info: { processed_frames, total_frames } }
      - SUCCESS  → añade annotated_video, csv_url, matches (conteo) y gallery (recortes)
      - FAILURE  → retorna { state: "FAILURE", … }
    """
    from celery.result import AsyncResult

    res = AsyncResult(job_id)
    info = res.info or {}
    data = {
        'state': res.state,
        'info': {
            'processed_frames': info.get('processed_frames', 0),
            'total_frames': info.get('total_frames', 0),
            'annotated_video': '',
            'csv_url': '',
            'matches': [],
            'gallery': []
        }
    }

    if res.state == 'SUCCESS':
        base_media = settings.MEDIA_URL.rstrip('/')
        annotated_rel = info.get('annotated_video', '')
        csv_rel = info.get('csv_path', '')
        results = info.get('results', [])
        gallery_rel = info.get('faces', [])

        enriched = []
        for item in results:
            pid = item.get('persona_id')
            cnt = item.get('count', 0)
            persona = Persona.objects.filter(pk=pid).first()
            if not persona:
                continue
            enriched.append({
                'id': pid,
                'dni': persona.dni,
                'nombre': f"{persona.nombre} {persona.apellidos}",
                'score': cnt
            })

        data['info']['annotated_video'] = f"{base_media}/{annotated_rel}" if annotated_rel else ''
        data['info']['csv_url'] = f"{base_media}/{csv_rel}" if csv_rel else ''
        data['info']['matches'] = enriched
        data['info']['gallery'] = [f"{base_media}/{face}" for face in gallery_rel]

    return JsonResponse(data)


@login_required
def ficha_policial(request, persona_id):
    """
    Recupera la Persona y renderiza ficha_policial.html con sus datos, direcciones,
    antecedentes y lista de embeddings.
    """
    persona = get_object_or_404(Persona, pk=persona_id)
    return render(request, 'recognition_face/ficha_policial.html', {'persona': persona})
