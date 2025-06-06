import re
import io
import cv2
import requests
import numpy as np
from ultralytics import YOLO

# -------------------------------------------------------------------
# CONFIGURACIÓN DE LA API DE PLATE RECOGNIZER
# -------------------------------------------------------------------
PLATE_API_URL = "https://api.platerecognizer.com/v1/plate-reader/"  # Endpoint para snapshot
PLATE_API_KEY = "cfb47be718a3a589612e21bdc2cc129e35f47903"           # Tu API key


# -------------------------------------------------------------------
# FUNCIONES AUXILIARES PARA DETECCIÓN
# -------------------------------------------------------------------


def detectar_vehiculos(frame: np.ndarray, model: YOLO) -> np.ndarray:
    """
    Ejecuta YOLOv8 sobre el frame completo para detectar vehículos.
    Filtra solo las clases: car, truck, bus, motorbike.
    Devuelve un array de shape (N, 5) con [x1, y1, x2, y2, score].
    """
    results = model(frame)[0]  # Ejecuta inferencia
    boxes = []
    for r in results.boxes.data.tolist():
        x1, y1, x2, y2, score, cls = r
        # Clases COCO para vehículos: 2=car, 5=bus, 7=truck, 3=motorbike
        if int(cls) in (2, 3, 5, 7):
            boxes.append([x1, y1, x2, y2, score])
    return np.array(boxes) if boxes else np.empty((0, 5))


def detectar_placa_en_roi(roi: np.ndarray, model: YOLO) -> np.ndarray:
    """
    Ejecuta YOLOv8 sobre el ROI del vehículo para detectar cajas de matrícula.
    Devuelve un array (idealmente de un solo elemento) con [x1, y1, x2, y2, score]
    en coordenadas relativas al ROI (no al frame completo). 
    Si no hay detecciones, devuelve array vacío.
    """
    results = model(roi)[0]
    boxes = []
    for r in results.boxes.data.tolist():
        x1, y1, x2, y2, score, cls = r
        # Asumimos que en el modelo de placas la clase 0 es la matrícula
        if int(cls) == 0:
            boxes.append([x1, y1, x2, y2, score])
    return np.array(boxes) if boxes else np.empty((0, 5))


# -------------------------------------------------------------------
# FUNCIONES PARA LLAMAR A LA API DE OCR
# -------------------------------------------------------------------

def llamar_api_ocr(plate_crop: np.ndarray) -> dict:
    """
    Envía la imagen (numpy array BGR) de la matrícula a Plate Recognizer y devuelve
    el JSON crudo con los resultados (lista de posibles plates con texto, score, country, etc.).
    """
    # Convertimos el recorte a JPEG en memoria
    _, buffer = cv2.imencode(".jpg", plate_crop)
    byte_im = io.BytesIO(buffer.tobytes())

    headers = {
        "Authorization": f"Token {PLATE_API_KEY}"
    }
    files = {
        "upload": ("plate.jpg", byte_im.getvalue())
    }
    try:
        resp = requests.post(PLATE_API_URL, headers=headers, files=files, timeout=5)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        # Si falla la petición, devolvemos un JSON vacío para que no parta todo
        return {}


# -------------------------------------------------------------------
# VALIDACIÓN DE MATRÍCULA POR PATRÓN Y PAÍS
# -------------------------------------------------------------------

# Patrón genérico: letras y/o dígitos (mínimo 4, máximo 8). 
# Se puede ampliar a otros patrones país a país. 
GENERIC_PLATE_REGEX = re.compile(r"^[A-Z0-9]{4,8}$")

def validar_matricula(ocr_json: dict) -> tuple[str, float]:
    """
    Recibe el JSON devuelto por Plate Recognizer.
    - Rechaza si 'country' es null o 'unknown'.
    - Aplica un patrón regex al texto de la matrícula.
    - Devuelve (texto_matricula, score) de la mejor coincidencia válida.
    Si no hay ninguna válida, devuelve (None, 0.0).
    """
    candidates = ocr_json.get("results", [])
    mejor_texto = None
    mejor_score = 0.0

    for c in candidates:
        country = c.get("plate", {}).get("region", None)
        text = c.get("plate", {}).get("plate", "").strip().upper()
        score = float(c.get("score", 0.0))

        # 1) País inválido → descartar
        if not country or country.lower() == "unknown":
            continue

        # 2) Patrones de validación (genérico, alfanumérico 4–8)
        if not GENERIC_PLATE_REGEX.match(text):
            continue

        # 3) Si cumple, quedarnos con la mejor score
        if score > mejor_score:
            mejor_score = score
            mejor_texto = text

    return (mejor_texto, mejor_score) if mejor_texto else (None, 0.0)
