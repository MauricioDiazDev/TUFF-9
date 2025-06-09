import os
import csv
import cv2
import numpy as np
from pathlib import Path
from celery import shared_task
from django.utils import timezone
from django.conf import settings
from personas.models import Persona
from .face_analysis import get_embedding
from .vector_index import search
from PIL import Image
from .face_analysis import detect_all_faces

UMBRAL_CONFIANZA = 0.65

@shared_task(bind=True)
def procesar_video_task(self, video_path,history_id, frame_step=10):
    """
    Procesa un vídeo frame a frame:
    - Cada N frames, detecta rostro más grande.
    - Extrae embedding y consulta en FAISS.
    - Si hay match ≥ 0.65, lo registra.
    - No se guarda el vídeo ni ningún archivo temporal salvo el CSV final.
    """
    cap = cv2.VideoCapture(video_path)
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    frame_idx = 0
    encontrados = {}

    # Crear carpeta CSV
    dir_csv = Path(settings.MEDIA_ROOT) / "recognition_face" / "csv"
    dir_csv.mkdir(parents=True, exist_ok=True)

    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    nombre_csv = f"reconocimiento_{timestamp}.csv"
    ruta_csv = dir_csv / nombre_csv

    with open(ruta_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['persona_id', 'dni', 'nombre', 'score'])

        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame_idx += 1

            if frame_idx % frame_step != 0:
                continue

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            embedding = get_embedding(rgb)
            if embedding is None:
                continue

            vecinos = search(embedding)
            if vecinos and vecinos[0][0] >= UMBRAL_CONFIANZA:
                sim, pid = vecinos[0]
                if pid not in encontrados:
                    persona = Persona.objects.filter(pk=pid).first()
                    if persona:
                        url_foto = persona.foto_principal.url if persona.foto_principal and hasattr(persona.foto_principal, 'url') else ''

                        encontrados[pid] = {
                            'id': persona.id,
                            'dni': persona.dni,
                            'nombre': f"{persona.nombre} {persona.apellidos}",
                            'score': round(sim, 4),
                            'foto': url_foto
                        }
                        writer.writerow([persona.id, persona.dni, persona.nombre, f"{sim:.4f}"])

            # Actualiza progreso aproximado
            self.update_state(state='PROGRESS', meta={'processed_frames': frame_idx, 'total_frames': total_frames})

    cap.release()

    # Eliminar el vídeo después del procesamiento
    try:
        os.remove(video_path)
    except Exception:
        pass

    from utilidades.models import SearchHistory
    result_count = len(encontrados)
    SearchHistory.objects.filter(id=history_id).update(result_count=result_count)

    return {
        'csv_path': os.path.relpath(ruta_csv, settings.MEDIA_ROOT),
        'resultados': list(encontrados.values())
    }



@shared_task(bind=True)
def procesar_imagenes_task(self, rutas_imagenes, history_id,descripcion=''):
    resultados = []
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    nombre_csv = f"reconocimiento_{timestamp}.csv"
    dir_csv = os.path.join(settings.MEDIA_ROOT, 'recognition_face', 'csv')
    os.makedirs(dir_csv, exist_ok=True)
    ruta_csv = os.path.join(dir_csv, nombre_csv)

    with open(ruta_csv, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(['persona_id', 'dni', 'nombre', 'score', 'origen'])

        for ruta in rutas_imagenes:
            try:
                img = Image.open(ruta).convert('RGB')
                arr = np.array(img)
                detecciones = detect_all_faces(arr)

                for _, embedding, _ in detecciones:
                    vecinos = search(embedding)
                    if vecinos and vecinos[0][0] >= UMBRAL_CONFIANZA:
                        sim, pid = vecinos[0]
                        persona = Persona.objects.filter(pk=pid).first()
                        if not persona:
                            continue

                        url_foto = persona.foto_principal.url if persona.foto_principal and hasattr(persona.foto_principal, 'url') else ''

                        writer.writerow([
                            persona.id,
                            persona.dni,
                            f"{persona.nombre} {persona.apellidos}",
                            f"{sim:.4f}",
                            os.path.basename(ruta)
                        ])

                        resultados.append({
                            'id': persona.id,
                            'dni': persona.dni,
                            'nombre': f"{persona.nombre} {persona.apellidos}",
                            'score': round(sim, 4),
                            'foto': url_foto
                        })

            except Exception:
                continue
            finally:
                try:
                    os.remove(ruta)
                except Exception:
                    pass

    # Eliminar duplicados por ID
    personas_unicas = {}
    for r in resultados:
        personas_unicas[r['id']] = r

    from utilidades.models import SearchHistory
    result_count = len(personas_unicas)
    SearchHistory.objects.filter(id=history_id).update(result_count=result_count)
    
    return {
        'descripcion': descripcion,
        'csv_path': os.path.relpath(ruta_csv, settings.MEDIA_ROOT),
        'resultados': list(personas_unicas.values())
    }

