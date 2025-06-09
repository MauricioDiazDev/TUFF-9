# recognition_plate/tasks_plate.py

from matriculas.models import Matricula
from personas.models import Persona
from django.utils import timezone
import os
import cv2
import numpy as np
import requests
from recognition_plate.sort.sort import iou_batch
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
DETECTION_THRESHOLD_VEH = 0.40
DETECTION_THRESHOLD_PLATE = 0.65
MIN_REGION_SCORE = 0.3

# Ruta a los pesos de YOLOv8 (vehículos y placas)
WEIGHTS_DIR = Path(settings.BASE_DIR) / "recognition_plate" / "models"
WEIGHTS_VEH = WEIGHTS_DIR / "yolov8x.pt"
WEIGHTS_PLATE = WEIGHTS_DIR / "license_plate_yolov8.pt"

#ruta de fotos anotadas
ANNOTATED_DIR = Path(settings.MEDIA_ROOT) / "recognition_plate" / "annotated"
ANNOTATED_DIR.mkdir(parents=True, exist_ok=True)

# API de Plate Recognizer
OCR_API_URL = settings.OCR_API_URL  
OCR_API_TOKEN = settings.PLATE_RECOGNIZER_TOKEN

# Directorio para guardar el CSV
CSV_DIR = Path(settings.MEDIA_ROOT) / "recognition_plate" / "csv"
os.makedirs(CSV_DIR, exist_ok=True)

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
        raw_region = top.get("region")
        if isinstance(raw_region, list) and raw_region:
            region_obj   = raw_region[0]
            country      = region_obj.get("value", "").upper()
            region_score = region_obj.get("score", 0.0)
        elif isinstance(raw_region, dict):
            country      = raw_region.get("code", "").upper()
            region_score = raw_region.get("score", 0.0)
        else:
            logger.debug(f"[OCR] Región no reconocida para track {track_id}, se omite")
            continue


        if not country or country.lower() == "unknown" or region_score < MIN_REGION_SCORE:
            logger.debug(
                f"[OCR] País '{country}' con confianza región={region_score:.3f} para track {track_id} → se omite"
            )
            continue

        plate_text = top.get("plate").upper()
        conf_plate = top.get("score", 0.0)

        if not plate_text:
            logger.debug(f"[OCR] Placa vacía para track {track_id}, se omite")
            continue

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
def process_video_plate(self, video_path, history_id):
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
      7) Guarda un CSV con (track_id, placa, país, confianza, frame, imagen) para tracks válidos.
      8) Genera imágenes anotadas por cada placa detectada.
      9) Borra el vídeo original y limpia temporales.
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

    # Para almacenar la mejor detección de placa por track
    best_plate_per_track = {}
    frame_idx = 0

    # 4) Procesar cada frame, saltando FRAME_SKIP
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        frame_idx += 1

        if (frame_idx - 1) % FRAME_SKIP != 0:
            continue

        processed_frames += 1

        # 4.1) Detectar vehículos
        results_veh = veh_model(frame, device=0, imgsz=(800, 800), conf=DETECTION_THRESHOLD_VEH)[0]
        dets = []
        for box, cls, conf in zip(results_veh.boxes.xyxy, results_veh.boxes.cls, results_veh.boxes.conf):
            cls_int = int(cls)
            if cls_int in (2, 3, 5, 7):
                x1, y1, x2, y2 = map(int, box.tolist())
                dets.append([x1, y1, x2, y2, float(conf)])
        dets_array = np.array(dets) if dets else np.empty((0, 5))

        # 4.2) Actualizar SORT
        tracks = sort_tracker.update(dets_array)

        # 4.3) Extraer crops de vehículos
        H, W = frame.shape[:2]
        rois_for_batch = []
        for trk in tracks:
            x1, y1, x2, y2, tid = trk
            tid = int(tid)
            x1c, y1c = max(0, int(x1)), max(0, int(y1))
            x2c, y2c = min(W, int(x2)), min(H, int(y2))
            if (x2c - x1c) < 30 or (y2c - y1c) < 30:
                continue
            crop_bgr = frame[y1c:y2c, x1c:x2c]
            if crop_bgr.size == 0:
                continue
            rois_for_batch.append((tid, frame_idx, x1c, y1c, x2c, y2c, crop_bgr))

        # 4.4) Detectar placas en batch
        if rois_for_batch:
            crops_batch = [item[6] for item in rois_for_batch]
            results_plate = plate_model(crops_batch, device=0, imgsz=(640, 640),
                                        conf=DETECTION_THRESHOLD_PLATE, batch=True)
            # 4.5) Evaluar cada resultado
            for i, res in enumerate(results_plate):
                tid, fidx, x1c, y1c, x2c, y2c, _ = rois_for_batch[i]
                if res.boxes.shape[0] == 0:
                    continue
                best_conf = 0.0
                best_box = None
                for box, conf in zip(res.boxes.xyxy, res.boxes.conf):
                    c = float(conf)
                    if c > best_conf:
                        best_conf = c
                        best_box = box.cpu().numpy()
                if best_box is None:
                    continue
                bx1c, by1c, bx2c, by2c = map(int, best_box.tolist())

                abs_bx1 = x1c + bx1c
                abs_by1 = y1c + by1c
                abs_bx2 = x1c + bx2c
                abs_by2 = y1c + by2c

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

        # 4.6) Reportar progreso
        self.update_state(
            state="PROGRESS",
            meta={"processed_frames": processed_frames, "total_frames": total_frames}
        )

    cap.release()

    # 5) Preparar anotaciones
    final_frames = {}  
    video_base = Path(video_path).stem

    # 6) Reabrir vídeo y recopilar crops finales
    cap2 = cv2.VideoCapture(video_path)
    ocr_requests = []
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
            logger.debug(f"[DEBUG] Cropped area vacía para track {tid}")
            continue
        ocr_requests.append((tid, fidx, crop_final))
        final_frames[tid] = (frame_f, (bx1, by1, bx2, by2))
    cap2.release()

    # 7) Llamar a OCR batch
    ocr_results = call_plate_recognizer_batch(ocr_requests)

    # 8) Anotar y guardar imágenes de vídeo
    for tid, res in ocr_results.items():
        frame_full, (bx1, by1, bx2, by2) = final_frames[tid]
        h, w = frame_full.shape[:2]

        # 1) Padding del 20 %
        pad_x = int((bx2 - bx1) * 0.2)
        pad_y = int((by2 - by1) * 0.2)

        # Limitar a bordes de la imagen
        x1p = max(0, bx1 - pad_x)
        y1p = max(0, by1 - pad_y)
        x2p = min(w, bx2 + pad_x)
        y2p = min(h, by2 + pad_y)

        # 2) Recorte centrado en el vehículo
        crop_full = frame_full[y1p:y2p, x1p:x2p]

        # 3) Dibujar sobre ese recorte, usando coords relativas
        # Ajustamos las coords originales restando x1p/y1p
        rx1, ry1 = bx1 - x1p, by1 - y1p
        rx2, ry2 = bx2 - x1p, by2 - y1p

        annotated = crop_full.copy()
        cv2.rectangle(annotated, (rx1, ry1), (rx2, ry2), (0, 255, 0), 2)
        cv2.putText(
            annotated,
            res["plate"],
            (rx1, ry1 - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 255, 0),
            2
        )

        # **BBDD**: creación/actualización de Matricula y asignación de Persona
        matricula, creada = Matricula.objects.get_or_create(numero=res["plate"])
        matricula.pais = res["country"].upper()
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

        filename = f"{video_base}_track_{tid}_anotada.jpg"
        path_out = ANNOTATED_DIR / filename
        # Logging diagnóstico: ruta de archivo
        logger.debug(f"[OCR] Guardando imagen anotada en: {path_out}")

        # Guardar la imagen anotada
        cv2.imwrite(str(path_out), annotated)

    # 9) Guardar CSV con columna 'imagen'
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"placas_{timestamp}.csv"
    csv_full = Path(settings.MEDIA_ROOT) / CSV_DIR / csv_filename
    with open(csv_full, "w", encoding="utf-8") as fcsv:
        fcsv.write("track_id,plate,country,confidence,frame,imagen\n")
        for tid, info in best_plate_per_track.items():
            if tid not in ocr_results:
                continue
            rr = ocr_results[tid]
            imagen = f"{video_base}_track_{tid}"
            line = (
                f"{tid},{rr['plate']},{rr['country']},"
                f"{rr['confidence']:.3f},{rr['frame']},{imagen}\n"
            )
            fcsv.write(line)

    # 10) Limpiar vídeo y temporales
    try:
        os.remove(video_path)
    except Exception:
        pass
    tmp_dir = Path(settings.MEDIA_ROOT) / "recognition_plate" / "tmp"
    for item in tmp_dir.glob("*"):
        try:
            item.unlink()
        except Exception:
            pass

    from utilidades.models import SearchHistory
    # número de placas reconocidas
    result_count = len(ocr_results)
    SearchHistory.objects.filter(id=history_id).update(result_count=result_count)

    # 11) Devolver sólo la ruta al CSV
    return {
        "csv_unicas": csv_filename
    }


@shared_task(bind=True)
def process_image_plate(self, rutas_imagenes, history_id):
    # Umbrales
    DETECTION_THRESHOLD_PLATE = 0.45
    IOU_CLUSTER_THRESH        = 0.5

    # Paths
    WEIGHTS_PLATE = Path(settings.BASE_DIR) / "recognition_plate" / "models" / "license_plate_yolov8.pt"

    # Carga modelo de placas
    plate_model = YOLO(str(WEIGHTS_PLATE))

    resultados_csv = []

    for img_path in rutas_imagenes:
        nombre_img = Path(img_path).name
        print(f"\n🖼️ Procesando imagen: {nombre_img}")
        img = cv2.imread(img_path)
        if img is None:
            print(f"⚠️ No se pudo cargar {img_path}")
            continue

        # 1️⃣ Detectar todas las placas en la imagen
        res = plate_model(img, device=0, imgsz=(800,800), conf=DETECTION_THRESHOLD_PLATE)[0]
        boxes = [list(map(int,box.cpu().numpy())) for box in res.boxes.xyxy]
        confs = [float(c) for c in res.boxes.conf]
        print(f"[DEBUG] placas detectadas (raw): {boxes} con confs {confs}")

        # 2️⃣ Clustering IoU para unificar detecciones solapadas
        placas = []; placas_confs = []
        used = set()
        for i in range(len(boxes)):
            if i in used: 
                continue
            cluster = [i]
            for j in range(i+1, len(boxes)):
                if j in used: 
                    continue
                bbi = np.array(boxes[i], dtype=float).reshape(1,4)
                bbj = np.array(boxes[j], dtype=float).reshape(1,4)
                if float(iou_batch(bbi,bbj)[0,0]) >= IOU_CLUSTER_THRESH:
                    cluster.append(j)
                    used.add(j)
            best = max(cluster, key=lambda k: confs[k])
            placas.append(boxes[best])
            placas_confs.append(confs[best])
        print(f"[DEBUG] placas post-cluster: {placas} con confs {placas_confs}")

        placas_finales = {}

        # 3️⃣ OCR por cada placa única
        for idx, ((x1,y1,x2,y2), pc) in enumerate(zip(placas, placas_confs)):
            print(f"[DEBUG] Placa {idx}: bbox={(x1,y1,x2,y2)}, conf={pc}")
            crop = img[y1:y2, x1:x2]
            if crop.size==0:
                continue

            # Preprocesado ligero
            gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
            if gray.shape[1]<100:
                gray = cv2.resize(gray, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)

            success, buf = cv2.imencode(".jpg", gray)
            if not success:
                continue

            # Llamada OCR
            files   = {"upload":("plate.jpg",buf.tobytes(),"image/jpeg")}
            headers = {"Authorization":f"Token {OCR_API_TOKEN}"}
            with api_ocr_lock:
                resp = requests.post(OCR_API_URL, files=files, headers=headers, timeout=10)
                print(f"[DEBUG] OCR status={resp.status_code}")
                if not resp.ok:
                    print(f"⚠️ OCR no 2xx, salto")
                    continue
                data = resp.json()
                time.sleep(random.uniform(1.5,2.5))

            if not data.get("results"):
                continue

            top = data["results"][0]

            raw_region = top.get("region")
            if isinstance(raw_region, list) and raw_region:
                region_obj   = raw_region[0]
                country      = region_obj.get("value","").upper()
                region_score = region_obj.get("score", 0.0)
            elif isinstance(raw_region, dict):
                country      = raw_region.get("code","").upper()
                region_score = raw_region.get("score", 0.0)
            else:
                print(f"[DEBUG] Región no reconocida para placa {idx}, salto")
                continue

            if not country or country.lower()=="unknown" or region_score < MIN_REGION_SCORE:
                print(f"[DEBUG] Región '{country}' con score={region_score:.3f} < {MIN_REGION_SCORE}, salto")
                continue

            plate_text = top.get("plate","").upper().replace("-","").replace(" ","")
            score      = top.get("score",0.0)
            print(f"[DEBUG] OCR result {idx}: plate={plate_text}, score={score}, country={country}")

            key = f"{nombre_img}_placa_{idx}"
            placas_finales[key] = {
                "plate": plate_text,
                "score": score,
                "country": country,
                "coords": (x1,y1,x2,y2),
                "imagen": nombre_img
            }

        print(f"[DEBUG] placas_finales keys={list(placas_finales.keys())}")

        # 4️⃣ Guardar resultados & anotar
        if placas_finales:
            annotated = img.copy()
            for d in placas_finales.values():
                x1,y1,x2,y2 = d["coords"]
                cv2.rectangle(annotated,(x1,y1),(x2,y2),(0,255,0),2)
                cv2.putText(annotated,d["plate"],(x1,y1-10),
                            cv2.FONT_HERSHEY_SIMPLEX,0.8,(0,255,0),2)
                # BBDD
                matricula, creada = Matricula.objects.get_or_create(numero=d["plate"])
                matricula.pais = d["country"].upper()
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
                resultados_csv.append((d["plate"],d["country"],d["score"],d["imagen"]))

            out_path = ANNOTATED_DIR / f"{Path(nombre_img).stem}_anotada.jpg"
            cv2.imwrite(str(out_path), annotated)

    # 5️⃣ Volcado CSV y limpieza
    print(f"[DEBUG] total resultados_csv={len(resultados_csv)}")
    timestamp = timezone.now().strftime("%Y%m%d_%H%M%S")
    csv_filename = f"placas_{timestamp}.csv"
    csv_full = Path(settings.MEDIA_ROOT) / CSV_DIR / csv_filename
    with open(csv_full,"w",encoding="utf-8") as f:
        f.write("plate,country,confidence,imagen\n")
        for plate,country,score,img in resultados_csv:
            f.write(f"{plate},{country},{score:.3f},{img}\n")

    for p in rutas_imagenes:
        try: os.remove(p)
        except: pass

    # === LIMPIEZA DE TODO EL DIRECTORIO tmp/imagenes ===
    tmp_img_dir = Path(settings.MEDIA_ROOT) / "recognition_plate" / "tmp" / "imagenes"
    if tmp_img_dir.exists():
        for f in tmp_img_dir.glob("*"):
            try:
                f.unlink()
            except:
                pass

    from utilidades.models import SearchHistory
    result_count = len(resultados_csv)
    SearchHistory.objects.filter(id=history_id).update(result_count=result_count)
    return {"total_imagenes":len(rutas_imagenes),"csv_unicas": csv_filename}