import numpy as np
import insightface
from insightface.app import FaceAnalysis
from typing import Optional, Tuple, List

# ------------------------------------------------------------------------------------
# Inicialización de InsightFace “buffalo_l” en GPU:
#   - name="buffalo_l": usa SCRFD para detección + ArcFace-R50 para embeddings
#   - allowed_modules=['detection','recognition']
#   - ctx_id=0 obliga a GPU; si no hay GPU o CUDA, lanza excepción y detiene el servicio
#   - det_size=(640,640) define resolución de detección
# ------------------------------------------------------------------------------------
face_app = FaceAnalysis(name="buffalo_l", allowed_modules=['detection', 'recognition'])
try:
    face_app.prepare(ctx_id=0, det_size=(640, 640))
except Exception as e:
    raise RuntimeError("No se pudo inicializar InsightFace buffalo_l en GPU: " + str(e))


def get_face_box(img_rgb: np.ndarray) -> Optional[Tuple[int, int, int, int]]:
    """
    Detecta el rostro más grande en una imagen RGB y devuelve su bounding box.
    Retorna (x1, y1, x2, y2) como enteros, recortados dentro de la imagen.
    Si no encuentra rostro, retorna None.
    """
    faces = face_app.get(img_rgb)
    if not faces:
        return None

    def area(f):
        x1, y1, x2, y2 = f.bbox
        return (x2 - x1) * (y2 - y1)

    face = max(faces, key=area)
    x1, y1, x2, y2 = face.bbox.astype(int)

    height, width = img_rgb.shape[:2]
    x1 = max(0, min(x1, width - 1))
    y1 = max(0, min(y1, height - 1))
    x2 = max(0, min(x2, width - 1))
    y2 = max(0, min(y2, height - 1))

    return (x1, y1, x2, y2)


def get_embedding(img_rgb: np.ndarray) -> Optional[np.ndarray]:
    """
    Extrae el embedding (512-d) del rostro más grande en img_rgb.
    Si no detecta rostro, retorna None.
    """
    faces = face_app.get(img_rgb)
    if not faces:
        return None

    def area(f):
        x1, y1, x2, y2 = f.bbox
        return (x2 - x1) * (y2 - y1)

    face = max(faces, key=area)
    return face.embedding


def detect_all_faces(img_rgb: np.ndarray) -> List[Tuple[Tuple[int, int, int, int], np.ndarray, float]]:
    """
    Detecta todos los rostros en una imagen RGB y devuelve lista de:
      [ ((x1,y1,x2,y2), embedding (512-d), det_score ), … ]
    Si no detecta nada, retorna lista vacía.
    """
    faces = face_app.get(img_rgb)
    resultados = []

    for f in faces:
        x1, y1, x2, y2 = f.bbox.astype(int)
        height, width = img_rgb.shape[:2]
        x1 = max(0, min(x1, width - 1))
        y1 = max(0, min(y1, height - 1))
        x2 = max(0, min(x2, width - 1))
        y2 = max(0, min(y2, height - 1))

        embedding = f.embedding
        score = float(f.det_score)
        resultados.append(((x1, y1, x2, y2), embedding, score))

    return resultados
