import os
import csv
import numpy as np
from celery import shared_task
from django.conf import settings
from django.utils import timezone
from PIL import Image

from personas.models import Persona
from .face_analysis import detect_all_faces
from .vector_index import search

UMBRAL_CONFIANZA = 0.65


@shared_task(bind=True)
def procesar_imagenes_task(self, rutas_imagenes, descripcion=''):
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

    return {
        'descripcion': descripcion,
        'csv_path': os.path.relpath(ruta_csv, settings.MEDIA_ROOT),
        'resultados': list(personas_unicas.values())
    }
