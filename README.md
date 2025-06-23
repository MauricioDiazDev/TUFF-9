# TUFF-9

**Facial and License Plate Recognition System**

TUFF-9 is a Django-based web platform for access control and identity recognition. It integrates real-time facial and vehicle license plate recognition using modern deep learning models, asynchronous background processing, and a user-friendly web interface for managing identities and search results.

---

## 🚀 Features

### 🔍 Facial Recognition
- Uses [InsightFace](https://github.com/deepinsight/insightface) with the `buffalo_l` model (SCRFD + ArcFace R50).
- Embedding similarity search with FAISS (GPU-accelerated).
- Supports image and video analysis.
- Asynchronous execution with Celery.

### 🚗 License Plate Recognition
- Dual YOLOv8 models: one for vehicle detection, one for plate detection.
- Object tracking powered by [SORT](https://github.com/abewley/sort).
- OCR via external API (e.g., Plate Recognizer).
- Annotated plate records with country and confidence filtering.

### ⚙️ Background Processing
- Scalable processing via Celery workers.
- Efficient task queuing and execution with Redis (if used).
- Results stored in CSV format and searchable via the web interface.

---

## 🧰 Technologies Used

| Tech            | Purpose                          |
|-----------------|----------------------------------|
| **Python**      | Core backend language            |
| **Django**      | Web framework                    |
| **Celery**      | Task queue / async processing    |
| **FAISS**       | Embedding search for faces       |
| **InsightFace** | Face detection and recognition   |
| **YOLOv8**      | Object/plate detection           |
| **SORT**        | Multi-object vehicle tracking    |
| **OCR API**     | License plate text extraction    |
| **OpenCV**      | Video and image processing       |
| **Pillow**      | Image handling                   |
| **HTML/CSS**    | Frontend interface               |

---

## 🧠 Recognition Models

| Task                | Model                       | Source                                                                              |
|---------------------|-----------------------------|-------------------------------------------------------------------------------------|
| Face Recognition    | `buffalo_l` (ArcFace R50)   | [InsightFace](https://github.com/deepinsight/insightface)                          |
| Vehicle Detection   | YOLOv8x                     | [Ultralytics](https://github.com/ultralytics/ultralytics)                          |
| License Plate       | YOLOv8 (custom-trained)     | Local models                                                                        |
| Tracking            | SORT                        | [SORT GitHub](https://github.com/abewley/sort)                                     |
| OCR                 | External API                | e.g. [Plate Recognizer](https://platerecognizer.com/) or similar services          |


