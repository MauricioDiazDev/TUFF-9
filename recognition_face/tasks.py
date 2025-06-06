import os
import csv
import cv2
from pathlib import Path
from celery import shared_task
from django.conf import settings
import numpy as np
import ffmpeg

from .face_analysis import get_embedding, get_face_box
from .vector_index import search
from personas.models import Persona

# Umbral fijo de similitud (coseno)
UMBRAL_CONFIANZA = 0.65


@shared_task(bind=True)
def process_video(self, video_path, frame_step=10):
    """
    Procesa un vídeo:
      1. Abre el vídeo para contar frames, FPS, dimensiones.
      2. Crea carpetas: annotated, csv, faces.
      3. Recorre frame a frame (saltándose frame_step):
         - Extrae embedding de la cara más grande.
         - Busca vecinos en FAISS (centroide + individuales).
         - Si sim >= 0.65: anota rectángulo, texto y cuenta apariciones.
         - Si es la primera aparición, guarda recorte de cara.
      4. Recodifica a H.264 con FFmpeg.
      5. Genera CSV con persona_id, dni, nombre, count.
      6. Retorna dict con rutas relativas y conteos.
    """
    # 1) Obtener propiedades del vídeo
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 25
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    cap.release()

    # 2) Crear directorios en MEDIA_ROOT
    base_media = settings.MEDIA_ROOT
    annotated_dir = Path(base_media) / "recognition_face" / "videos" / "annotated"
    csv_dir = Path(base_media) / "recognition_face" / "csv"
    faces_dir = Path(base_media) / "recognition_face" / "faces"
    for d in (annotated_dir, csv_dir, faces_dir):
        d.mkdir(parents=True, exist_ok=True)

    base_name = Path(video_path).stem
    unique_base = f"{base_name}_{self.request.id}"
    raw_annotated_path = annotated_dir / f"{unique_base}.tmp.mp4"
    final_annotated_path = annotated_dir / f"{unique_base}_annotated.mp4"
    csv_path = csv_dir / f"{unique_base}_results.csv"

    # 3) Configurar VideoWriter
    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
    writer = cv2.VideoWriter(str(raw_annotated_path), fourcc, fps, (w, h))

    counts = {}       # { persona_id: total_count }
    face_samples = {} # { persona_id: ruta_rel_primer_recorte }

    cap = cv2.VideoCapture(video_path)
    frame_idx = 0

    self.update_state(state='PROGRESS', meta={'processed_frames': 0, 'total_frames': total_frames})

    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1

        if frame_idx % frame_step == 0:
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            embedding = get_embedding(rgb)
            if embedding is not None:
                vecinos = search(embedding)
                if vecinos and vecinos[0][0] >= UMBRAL_CONFIANZA:
                    sim, pid = vecinos[0]
                    counts[pid] = counts.get(pid, 0) + 1

                    box = get_face_box(rgb)
                    if box:
                        x1, y1, x2, y2 = box
                        persona = Persona.objects.filter(pk=pid).first()

                        cv2.rectangle(frame, (x1, y1), (x2, y2), (0, 255, 0), 2)
                        texto = f"{persona.nombre} {persona.apellidos} ({sim:.2f})"
                        cv2.putText(frame, texto, (x1, y1 - 10),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

                        if pid not in face_samples:
                            face_crop = frame[y1:y2, x1:x2]
                            face_filename = f"face_{pid}_{unique_base}.jpg"
                            face_path = faces_dir / face_filename
                            cv2.imwrite(str(face_path), face_crop)
                            rel_face = f"recognition_face/faces/{face_filename}"
                            face_samples[pid] = rel_face

            processed = frame_idx // frame_step
            self.update_state(state='PROGRESS', meta={'processed_frames': processed, 'total_frames': total_frames})

        writer.write(frame)

    cap.release()
    writer.release()

    # 4) Recodificar a H.264
    try:
        (
            ffmpeg
            .input(str(raw_annotated_path))
            .output(
                str(final_annotated_path),
                vcodec='libx264',
                pix_fmt='yuv420p',
                movflags='+faststart'
            )
            .overwrite_output()
            .run(quiet=True)
        )
        raw_annotated_path.unlink()
    except Exception:
        final_annotated_path = raw_annotated_path

    # 5) Generar CSV de conteos
    with open(csv_path, 'w', newline='', encoding='utf-8') as csvfile:
        writer_csv = csv.writer(csvfile)
        writer_csv.writerow(['persona_id', 'dni', 'nombre', 'count'])
        for pid, cnt in counts.items():
            persona = Persona.objects.filter(pk=pid).first()
            if not persona:
                continue
            writer_csv.writerow([pid, persona.dni, f"{persona.nombre} {persona.apellidos}", cnt])

    # 6) Rutas relativas a MEDIA_ROOT
    rel_annotated = os.path.relpath(str(final_annotated_path), settings.MEDIA_ROOT)
    rel_csv = os.path.relpath(str(csv_path), settings.MEDIA_ROOT)
    gallery = list(face_samples.values())

    return {
        'processed_frames': processed,
        'total_frames': total_frames,
        'results': [{'persona_id': pid, 'count': cnt} for pid, cnt in counts.items()],
        'annotated_video': rel_annotated,
        'csv_path': rel_csv,
        'faces': gallery
    }
