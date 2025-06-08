#recognition_face/vector_index.py
import faiss
import numpy as np
from personas.models import EmbeddingPersona, CentroidePersona

EMB_DIM = 512       # dimensión de los embeddings de ArcFace-R50
TOP_K = 5           # top_k vecinos a recuperar

_gpu_index = None   # índice FAISS (GPU o CPU)
_id_map = []        # lista de persona IDs en el mismo orden que los vectores


def build_faiss_index_gpu():
    """
    Construye (o reconstruye) el índice FAISS con:
      1) Primero, todos los centroides (uno por persona, si existe).
      2) Luego, todos los embeddings individuales (para casos extremos).
    Usa IndexFlatIP si hay pocos vectores (<16), o IndexIVFFlat en CPU + GPU.
    """
    global _gpu_index, _id_map
    embeddings = []
    _id_map = []

    # 1) Insertar todos los centroides primero
    for c in CentroidePersona.objects.select_related('persona'):
        vec = np.array(c.embedding_promedio, dtype='float32')
        if vec.shape[0] == EMB_DIM:
            embeddings.append(vec)
            _id_map.append(c.persona.id)

    # 2) Insertar embeddings individuales (casos extremos)
    for ep in EmbeddingPersona.objects.select_related('persona').all():
        vec = np.array(ep.embedding, dtype='float32')
        norma = np.linalg.norm(vec)
        if norma > 0:
            embeddings.append(vec / norma)
            _id_map.append(ep.persona.id)

    # Si no hay vectores, retornar índice vacío
    if not embeddings:
        cpu_index = faiss.IndexFlatIP(EMB_DIM)
        try:
            res = faiss.StandardGpuResources()
            _gpu_index = faiss.index_cpu_to_gpu(res, 0, cpu_index)
        except AttributeError:
            _gpu_index = cpu_index
        return _gpu_index, _id_map

    # Apilar y normalizar L2
    xb = np.stack(embeddings, axis=0).astype('float32')
    faiss.normalize_L2(xb)

    n_data = xb.shape[0]
    if n_data < 16:
        # Índice plano exacto para pocos vectores
        cpu_index = faiss.IndexFlatIP(EMB_DIM)
        cpu_index.add(xb)
    else:
        # Índice IVF en CPU
        nlist = max(1, int(np.sqrt(n_data)))
        quantizer = faiss.IndexFlatL2(EMB_DIM)
        cpu_index = faiss.IndexIVFFlat(
            quantizer,
            EMB_DIM,
            nlist,
            faiss.METRIC_INNER_PRODUCT
        )
        cpu_index.train(xb)
        cpu_index.add(xb)

    # Intentar pasar a GPU
    try:
        res = faiss.StandardGpuResources()
        _gpu_index = faiss.index_cpu_to_gpu(res, 0, cpu_index)
    except AttributeError:
        _gpu_index = cpu_index

    return _gpu_index, _id_map


def get_faiss_index():
    """
    Retorna (_gpu_index, _id_map). Si el índice no existe o está vacío,
    lo reconstruye llamando a build_faiss_index_gpu().
    """
    global _gpu_index, _id_map
    if _gpu_index is None or (_gpu_index is not None and hasattr(_gpu_index, 'ntotal') and _gpu_index.ntotal == 0):
        return build_faiss_index_gpu()
    return _gpu_index, _id_map


def search(embedding: np.ndarray, top_k: int = TOP_K):
    """
    Busca los top_k vecinos más similares en el índice.
    Retorna lista de (score, persona_id), ordenada por score descendente.
    Si el índice está vacío, retorna lista vacía.
    """
    ix, id_map = get_faiss_index()
    if ix is None or ix.ntotal == 0:
        return []

    xq = np.array([embedding], dtype='float32')
    faiss.normalize_L2(xq)

    # Si el índice es IVF, aumentamos nprobe para mayor cobertura
    if hasattr(ix, 'nprobe'):
        ix.nprobe = 30

    D, I = ix.search(xq, top_k)
    results = []
    for sim, idx in zip(D[0], I[0]):
        if 0 <= idx < len(id_map):
            results.append((float(sim), id_map[idx]))
    return results
