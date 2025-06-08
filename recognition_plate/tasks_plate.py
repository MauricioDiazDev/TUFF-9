# recognition_plate/tasks_plate.py

from matriculas.models import Matricula
from personas.models import Persona
from django.utils import timezone
import os
import cv2
import numpy as np
import requests
from pathlib import Path
from recognition_plate.api_lock import api_ocr_lock
import random


from celery import shared_task
from celery.utils.log import get_task_logger

from django.conf import settings
import time
# Asegúrate de que el directorio `recognition_plate/sort/` tenga un __init__.py
# y que allí esté el archivo sort.py con la clase Sort.
from .sort.sort import Sort

# Usamos Ultralytics YOLOv8
from ultralytics import YOLO

logger = get_task_logger(__name__)

# ---------------------------------------
#  CONFIGURACIÓN Y CONSTANTES
# ---------------------------------------

# Umbrales de detección
DETECTION_THRESHOLD_VEH = 0.60
DETECTION_THRESHOLD_PLATE = 0.65

# Ruta a los pesos de YOLOv8 (vehículos y placas)
WEIGHTS_DIR = Path(settings.BASE_DIR) / "recognition_plate" / "models"
WEIGHTS_VEH = WEIGHTS_DIR / "vehiculos_yolov8n.pt"
WEIGHTS_PLATE = WEIGHTS_DIR / "license_plate_yolov8.pt"

# API de Plate Recognizer
OCR_API_URL = "https://api.platerecognizer.com/v1/plate-reader/"  # Ajusta si tu endpoint es diferente
OCR_API_TOKEN = "742c6ede255a89388a40e99605f1be8c5bcc8d97"

# Directorio para guardar el CSV
CSV_DIR = Path(settings.MEDIA_ROOT) / "recognition_plate" / "csv"
os.makedirs(CSV_DIR, exist_ok=True)
CSV_UNICAS_REL = Path("recognition_plate") / "csv" / "placas_unicas.csv"

# Cuántos frames saltar entre cada detección
FRAME_SKIP = 3

# ---------------------------------------
#  FUNCIONES AUXILIARES
# ---------------------------------------

def call_plate_recognizer_batch(requests_list):
    """
    Llama a la API de Plate Recognizer para cada crop_final en requests_list.
    Sólo retorna aquellos resultados cuyo país no sea 'unknown' ni None.
    requests_list: lista de tuplas (track_id, frame_idx, crop_bgr_uint8)
    Devuelve diccionario { track_id: {country, plate, confidence, frame} }
    """
    headers = {"Authorization": f"Token {OCR_API_TOKEN}"}
    results = {}

    for track_id, frame_idx, crop_bgr in requests_list:
        # Codificar el crop como JPEG para enviarlo a la API
        success, buffer = cv2.imencode(".jpg", crop_bgr)
        if not success:
            logger.debug(f"[OCR] No se pudo codificar el recorte JPEG para track {track_id} en frame {frame_idx}")
            continue

        files = {"upload": ("plate.jpg", buffer.tobytes(), "image/jpeg")}

        with api_ocr_lock:
            try:
                resp = requests.post(OCR_API_URL, files=files, headers=headers, timeout=10)
                data = resp.json()
            except Exception as e:
                logger.error(f"[OCR] Error al llamar a la API para track {track_id}: {e}")
                continue
        
            time.sleep(random.uniform(1.5, 2.5))

        # La respuesta tiene la estructura {"results": [ { "plate": "...", "region": {"code": "ES"}, "confidence": 0.?? }, ... ] }
        if not data.get("results"):
            logger.debug(f"[OCR] No hay resultados de OCR para track {track_id} (frame {frame_idx})")
            continue

        top = data["results"][0]
        country = top.get("region", {}).get("code")
        if not country or country.lower() == "unknown":
            logger.debug(f"[OCR] País desconocido para track {track_id}: country='{country}' → se omite")
            continue

        plate_text = top.get("plate").upper()
        conf_plate = top.get("score", 0.0)
        results[track_id] = {
            "country": country,
            "plate": plate_text,
            "confidence": conf_plate,
            "frame": frame_idx
        }
        logger.debug(f"[OCR] Track {track_id} → plate='{plate_text}', country={country}, confidence={conf_plate:.3f}, frame={frame_idx}")

    return results


# ---------------------------------------
#  TAREA PRINCIPAL DE CELERY
# ---------------------------------------

@shared_task(bind=True)
def process_video_plate(self, video_path):
    """
    Tarea Celery que procesa un vídeo para detección y reconocimiento de matrículas:
      1) Comprueba que existen los pesos de YOLOv8.
      2) Abre el vídeo y cuenta frames.
      3) Carga ambos modelos YOLOv8 en GPU.
      4) Recorre el vídeo saltando FRAME_SKIP frames:
         4.1) Detecta vehículos (YOLOv8n) → extrae detecciones relevantes (coches, camiones, etc.)
         4.2) Actualiza SORT con esas detecciones.
         4.3) Para cada track activo, extrae un crop del rectángulo del vehículo. 
         4.4) Agrupa todos los crops en una lista (batch) y los pasa a YOLOv8-placas como arrays uint8.
         4.5) Para cada resultado de placa, mapea la caja de vuelta al frame completo y
              guarda únicamente si supera el umbral de confianza y es mejor que lo anterior.
      5) Tras procesar todos los frames, reabre el vídeo y, para cada track, extrae
         **solo una vez** el recorte final que tuvo mayor puntuación.
      6) Llama a la API de OCR en batch (una llamada por track_final) y filtra por país.
      7) Guarda un CSV con (track_id, placa, país, confianza, frame) únicamente para tracks válidos.
    """

    # 1) Verificar pesos YOLOv8
    if not WEIGHTS_VEH.exists() or not WEIGHTS_PLATE.exists():
        raise FileNotFoundError(
            "Faltan los pesos YOLOv8 en recognition_plate/models:\n"
            f"  {WEIGHTS_VEH}\n"
            f"  {WEIGHTS_PLATE}"
        )

    # 2) Abrir vídeo y contar frames
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise FileNotFoundError(f"No se pudo abrir el vídeo: {video_path}")

    total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    processed_frames = 0

    # 3) Cargar modelos YOLOv8 en GPU
    logger.info(f"[YOLO] Cargando modelo vehículos desde: {WEIGHTS_VEH}")
    veh_model = YOLO(str(WEIGHTS_VEH))
    logger.info(f"[YOLO] Cargando modelo placas desde: {WEIGHTS_PLATE}")
    plate_model = YOLO(str(WEIGHTS_PLATE))

    # 4) Instanciar SORT
    sort_tracker = Sort(max_age=1, min_hits=3, iou_threshold=0.3)

    # Diccionario donde guardamos, para cada track_id, su mejor caja de placa hasta ahora:
    # best_plate_per_track = {
    #   track_id: {
    #       "bbox": [abs_x1, abs_y1, abs_x2, abs_y2],
    #       "score": mejor_confianza_detect,
    #       "frame": frame_idx
    #   }
    # }
    best_plate_per_track = {}

    frame_idx = 0

    # 4) Procesar cada frame, saltando FRAME_SKIP
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1

        # Saltar frames según FRAME_SKIP
        if (frame_idx - 1) % FRAME_SKIP != 0:
            continue

        processed_frames += 1

        # 4.1) Detectar vehículos en GPU
        results_veh = veh_model(
            frame,
            device=0,
            imgsz=(800, 800),
            conf=DETECTION_THRESHOLD_VEH
        )[0]

        # Construimos array de detecciones [[x1,y1,x2,y2,conf], ...]
        dets = []
        for box, cls, conf in zip(results_veh.boxes.xyxy,
                                  results_veh.boxes.cls,
                                  results_veh.boxes.conf):
            cls_int = int(cls)
            # Filtrar únicamente las clases de vehículos que nos interesan:
            # (2:car, 3:motorbike, 5:bus, 7:truck)
            if cls_int in (2, 3, 5, 7):
                x1, y1, x2, y2 = map(int, box.tolist())
                dets.append([x1, y1, x2, y2, float(conf)])
        dets_array = np.array(dets) if dets else np.empty((0, 5))

        # 4.2) Actualizar SORT con esas detecciones
        tracks = sort_tracker.update(dets_array)

        # 4.3) Para cada track, extraer crop del vehículo
        H, W = frame.shape[:2]
        rois_for_batch = []  # Lista de tuplas (track_id, frame_idx, x1c, y1c, x2c, y2c, crop_bgr_uint8)

        for trk in tracks:
            x1, y1, x2, y2, tid = trk
            tid = int(tid)
            # Asegurarnos de que las coordenadas estén dentro de la imagen
            x1c, y1c = max(0, int(x1)), max(0, int(y1))
            x2c, y2c = min(W, int(x2)), min(H, int(y2))

            # Descartar detecciones demasiado pequeñas (ruido)
            if (x2c - x1c) < 30 or (y2c - y1c) < 30:
                continue

            crop_bgr = frame[y1c:y2c, x1c:x2c]
            if crop_bgr.size == 0:
                continue

            rois_for_batch.append((tid, frame_idx, x1c, y1c, x2c, y2c, crop_bgr))

        # 4.4) Si hay recortes, inferir en batch para detectar placas
        if rois_for_batch:
            crops_batch = [item[6] for item in rois_for_batch]  # lista de arrays uint8

            # YOLOv8-placa en GPU con batch
            results_plate = plate_model(
                crops_batch,
                device=0,
                imgsz=(640, 640),
                conf=DETECTION_THRESHOLD_PLATE,
                batch=True
            )

            # 4.5) Para cada resultado de placa en el batch:
            for i, res in enumerate(results_plate):
                tid, fidx, x1c, y1c, x2c, y2c, _ = rois_for_batch[i]

                # Si no hay cajas en este result, saltar
                if res.boxes.shape[0] == 0:
                    continue

                # Escoger la caja de mayor confianza dentro del crop
                best_conf = 0.0
                best_box = None  # En coordenadas [x1_crop, y1_crop, x2_crop, y2_crop]

                for box, conf in zip(res.boxes.xyxy, res.boxes.conf):
                    c = float(conf)
                    if c > best_conf:
                        best_conf = c
                        best_box = box.cpu().numpy()

                if best_box is None:
                    continue

                # best_box ya está en píxeles relativos al propio crop (uint8)
                bx1c, by1c, bx2c, by2c = map(int, best_box.tolist())

                # Mapear esa caja de vuelta al frame completo:
                abs_bx1 = x1c + bx1c
                abs_by1 = y1c + by1c
                abs_bx2 = x1c + bx2c
                abs_by2 = y1c + by2c

                # Comprobar si este lazo de track_id mejora lo que había antes
                prev = best_plate_per_track.get(tid)
                if (prev is None) or (best_conf > prev["score"]):
                    best_plate_per_track[tid] = {
                        "bbox": [abs_bx1, abs_by1, abs_bx2, abs_by2],
                        "score": best_conf,
                        "frame": fidx
                    }
                    logger.debug(
                        f"[DEBUG] Track {tid} → Nueva mejor placa: "
                        f"conf={best_conf:.3f}, frame={fidx}, "
                        f"bbox_abs=[{abs_bx1},{abs_by1},{abs_bx2},{abs_by2}]"
                    )

        # 4.6) Actualizar estado de Celery
        self.update_state(
            state="PROGRESS",
            meta={
                "processed_frames": processed_frames,
                "total_frames": total_frames
            }
        )

    cap.release()

    # 5) Reabrir el vídeo para extraer el recorte FINAL de cada track
    cap2 = cv2.VideoCapture(video_path)
    ocr_requests = []  # lista de (track_id, frame_idx, crop_final)

    for tid, info in best_plate_per_track.items():
        bx1, by1, bx2, by2 = info["bbox"]
        fidx = info["frame"]

        cap2.set(cv2.CAP_PROP_POS_FRAMES, fidx - 1)
        ret2, frame_f = cap2.read()
        if not ret2:
            logger.debug(f"[DEBUG] No se pudo leer frame {fidx} para track {tid}")
            continue

        crop_final = frame_f[by1:by2, bx1:bx2]
        if crop_final.size == 0:
            logger.debug(f"[DEBUG] Cropped area vacía para track {tid} en frame {fidx}")
            continue

        ocr_requests.append((tid, fidx, crop_final))

    cap2.release()

    # 6) Llamar a la API de OCR en batch (una llamada por track final)
    ocr_results = call_plate_recognizer_batch(ocr_requests)

    # 7) Guardar CSV con las placas válidas
    csv_full = Path(settings.MEDIA_ROOT) / CSV_UNICAS_REL
    with open(csv_full, "w", encoding="utf-8") as fcsv:
        fcsv.write("track_id,plate,country,confidence,frame\n")
        for tid, info in best_plate_per_track.items():
            if tid not in ocr_results:
                continue
            rr = ocr_results[tid]
            line = f"{tid},{rr['plate']},{rr['country']},{rr['confidence']:.3f},{rr['frame']}\n"
            fcsv.write(line)

    # 8) Devolver estado final a Celery
    return {
        "processed_frames": processed_frames,
        "total_frames": total_frames,
        "csv_unicas": str(CSV_UNICAS_REL)
    }


@shared_task(bind=True)
def process_image_plate(self, rutas_imagenes):

    DETECTION_THRESHOLD_VEH = 0.20
    DETECTION_THRESHOLD_PLATE = 0.65

    WEIGHTS_DIR = Path(settings.BASE_DIR) / "recognition_plate" / "models"
    WEIGHTS_VEH = WEIGHTS_DIR / "vehiculos_yolov8n.pt"
    WEIGHTS_PLATE = WEIGHTS_DIR / "license_plate_yolov8.pt"

    CSV_DIR = Path(settings.MEDIA_ROOT) / "recognition_plate" / "csv"
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    CSV_UNICAS = CSV_DIR / "placas_unicas.csv"

    ANNOTATED_DIR = Path(settings.MEDIA_ROOT) / "recognition_plate" / "annotated"
    ANNOTATED_DIR.mkdir(parents=True, exist_ok=True)

    OCR_API_URL = "https://api.platerecognizer.com/v1/plate-reader/"
    OCR_API_TOKEN = "742c6ede255a89388a40e99605f1be8c5bcc8d97"

    veh_model = YOLO(str(WEIGHTS_VEH))
    plate_model = YOLO(str(WEIGHTS_PLATE))

    resultados_csv = []

    for img_path in rutas_imagenes:
        nombre_img = Path(img_path).name
        print(f"\n🖼️ Procesando imagen: {nombre_img}")
        imagen = cv2.imread(img_path)
        if imagen is None:
            print(f"⚠️ No se pudo cargar la imagen: {img_path}")
            continue

        results_veh = veh_model(imagen, device=0, imgsz=(800, 800), conf=DETECTION_THRESHOLD_VEH)[0]
        vehiculos = [
            list(map(int, box.tolist()))
            for box, cls in zip(results_veh.boxes.xyxy, results_veh.boxes.cls)
            if int(cls) in (2, 3, 5, 7)
        ]
        print(f"🚗 Vehículos detectados: {len(vehiculos)}")

        placas_finales = {}

        for idx, (vx1, vy1, vx2, vy2) in enumerate(vehiculos):
            crop_veh = imagen[vy1:vy2, vx1:vx2]
            if crop_veh.size == 0:
                continue

            res_placa = plate_model([crop_veh], device=0, imgsz=(640, 640), conf=DETECTION_THRESHOLD_PLATE)[0]
            if len(res_placa.boxes) == 0:
                continue

            best_box = None
            best_conf = 0.0
            for box, conf in zip(res_placa.boxes.xyxy, res_placa.boxes.conf):
                c = float(conf)
                if c > best_conf:
                    best_box = box.cpu().numpy().astype(int)
                    best_conf = c

            if best_box is None:
                continue

            px1, py1, px2, py2 = best_box
            abs_px1, abs_py1, abs_px2, abs_py2 = vx1 + px1, vy1 + py1, vx1 + px2, vy1 + py2
            crop_placa = imagen[abs_py1:abs_py2, abs_px1:abs_px2]
            if crop_placa.size == 0:
                continue

            success, buffer = cv2.imencode(".jpg", crop_placa)
            if not success:
                continue

            files = {"upload": ("plate.jpg", buffer.tobytes(), "image/jpeg")}
            headers = {"Authorization": f"Token {OCR_API_TOKEN}"}

            with api_ocr_lock:
                try:
                    resp = requests.post(OCR_API_URL, files=files, headers=headers, timeout=10)
                    data = resp.json()
                except Exception as e:
                    print(f"🛑 Error OCR: {e}")
                    continue
                time.sleep(random.uniform(1.5, 2.5))

            if not data.get("results"):
                continue

            top = data["results"][0]
            plate = top.get("plate", "").upper().replace("-", "").replace(" ", "")
            score = top.get("score", 0.0)
            country = top.get("region", {}).get("code", "")

            if not plate or not country or country.lower() == "unknown":
                continue

            key = f"{nombre_img}_vehiculo_{idx}"
            placas_finales[key] = {
                "plate": plate,
                "score": score,
                "country": country,
                "coords": (abs_px1, abs_py1, abs_px2, abs_py2),
                "imagen": nombre_img
            }

        if placas_finales:
            img_annotated = imagen.copy()
            for data in placas_finales.values():
                plate = data["plate"]
                score = data["score"]
                country = data["country"]
                x1, y1, x2, y2 = data["coords"]

                matricula, creada = Matricula.objects.get_or_create(numero=plate)
                matricula.pais = country.upper()
                matricula.ultima_vez_vista = timezone.now()
                if creada:
                    personas = list(Persona.objects.all())
                    matricula.esta_robado = False
                    matricula.delitos = ""
                    matricula.save()
                    if personas:
                        matricula.propietarios.add(random.choice(personas))
                else:
                    matricula.save()

                resultados_csv.append((plate, country, score, data["imagen"]))
                cv2.rectangle(img_annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
                cv2.putText(img_annotated, plate, (x1, y1 - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

            out_path = ANNOTATED_DIR / f"{Path(nombre_img).stem}_anotada.jpg"
            cv2.imwrite(str(out_path), img_annotated)

        else:
            print("🕳️ No se anotó nada en la imagen.")

    with open(CSV_UNICAS, "w", encoding="utf-8") as f:
        f.write("plate,country,confidence,imagen\n")
        for r in resultados_csv:
            f.write(f"{r[0]},{r[1]},{r[2]:.3f},{r[3]}\n")

    for img_path in rutas_imagenes:
        try:
            os.remove(img_path)
        except Exception as e:
            print(f"⚠️ No se pudo borrar {img_path}: {e}")

    return {
        "total_imagenes": len(rutas_imagenes),
        "csv_unicas": str(CSV_UNICAS)
    }