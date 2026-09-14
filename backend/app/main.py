import io
import os
import sys
import time
import logging
from typing import Optional
from fastapi import FastAPI, File, UploadFile, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

load_dotenv()

# Backend kök dizinini sys.path'e ekle
BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, '..'))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from app.database import Database
from app.face_engine import FaceEngine
from app.drive_service import DriveService

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("api")

app = FastAPI(
    title="Fotoğraf Paylaşım & Yüz Eşleme Platformu API",
    description="Google Drive ve Face Recognition tabanlı 0 maliyetli etkinlik fotoğraf arama servisi",
    version="1.0.0"
)

# Mobil cihazların yerel ağdan (192.168.x.x vb.) veya farklı alan adlarından erişebilmesi için CORS izni
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tekil örnekler (Singletons)
db = Database()
face_engine = FaceEngine()
drive_service = DriveService()


@app.get("/api/health")
async def health_check():
    """Sistem durumunu, GPU cihazını ve veritabanı boyutunu döner."""
    stats = db.get_stats()
    return {
        "status": "online",
        "device": str(face_engine.device),
        "drive_connected": drive_service.is_connected(),
        "total_photos": stats["total_photos"],
        "total_faces": stats["total_faces"]
    }


@app.get("/api/stats")
async def get_stats():
    """İndekslenmiş fotoğraf ve yüz istatistiklerini döner."""
    return db.get_stats()


@app.post("/api/search")
async def search_by_selfie(
    file: UploadFile = File(..., description="Kullanıcının selfie fotoğrafı"),
    threshold: Optional[float] = Query(None, description="Kosinüs mesafesi eşiği (0.40 - 0.50 ideal)")
):
    """
    Kullanıcının yüklediği selfie'den yüz vektörünü çıkarır ve
    veritabanındaki tüm fotoğraflarla karşılaştırıp eşleşenleri döner.
    """
    start_time = time.time()

    # Eşik değerini belirle
    default_threshold = float(os.getenv("FACE_MATCH_THRESHOLD", 0.45))
    active_threshold = threshold if threshold is not None else default_threshold

    # Dosya türü kontrolü
    if not file.content_type.startswith("image/"):
        raise HTTPException(
            status_code=400,
            detail="Geçersiz dosya formatı. Lütfen bir görsel dosyası (JPEG, PNG vb.) yükleyin."
        )

    try:
        # 1. Yüklenen selfie dosyasını RAM'e oku
        contents = await file.read()
        image_stream = io.BytesIO(contents)

        # 2. Selfie'deki ana yüzü tespit et ve 512-D embedding'ini çıkar
        query_embedding = face_engine.extract_face_from_selfie(image_stream)
        if query_embedding is None:
            return JSONResponse(
                status_code=400,
                content={
                    "success": False,
                    "message": "Selfie fotoğrafında net bir yüz tespit edilemedi. Lütfen yüzünüzün aydınlık ve doğrudan kameraya baktığı bir fotoğraf yükleyin."
                }
            )

        # 3. Veritabanından tüm yüz vektörlerini çek
        face_ids, photo_ids, matrix = db.get_all_faces()
        if len(face_ids) == 0:
            return {
                "success": True,
                "total_matches": 0,
                "matches": [],
                "message": "Henüz albüme fotoğraf yüklenmemiş veya indekslenmemiş.",
                "execution_time_ms": round((time.time() - start_time) * 1000, 2)
            }

        # 4. Hızlı NumPy Kosinüs Benzerliği Karşılaştırması
        ranked_matches = face_engine.match_faces(
            query_embedding=query_embedding,
            face_ids=face_ids,
            photo_ids=photo_ids,
            embeddings_matrix=matrix,
            threshold=active_threshold
        )

        if not ranked_matches:
            return {
                "success": True,
                "total_matches": 0,
                "matches": [],
                "message": "Sizinle eşleşen bir fotoğraf bulunamadı. Dilerseniz farklı bir açıyla çekilmiş bir selfie deneyebilirsiniz.",
                "execution_time_ms": round((time.time() - start_time) * 1000, 2)
            }

        # 5. Eşleşen fotoğrafların detaylarını (URL'ler, dosya adı vb.) çek
        matched_photo_ids = [m["photo_id"] for m in ranked_matches]
        photos = db.get_photos_by_ids(matched_photo_ids)
        photo_dict = {p["id"]: p for p in photos}

        results = []
        for match in ranked_matches:
            p_id = match["photo_id"]
            if p_id in photo_dict:
                photo_info = photo_dict[p_id]
                results.append({
                    "id": photo_info["id"],
                    "filename": photo_info["filename"],
                    "view_url": photo_info["view_url"],
                    "download_url": photo_info["download_url"],
                    "match_score": match["match_score"],
                    "distance": round(match["distance"], 4)
                })

        duration = round((time.time() - start_time) * 1000, 2)
        logger.info(f"Arama tamamlandı: {len(results)} eşleşme bulundu. Süre: {duration} ms")

        return {
            "success": True,
            "total_matches": len(results),
            "matches": results,
            "execution_time_ms": duration
        }

    except Exception as e:
        logger.error(f"Arama sırasında hata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Arama işlemi sırasında bir hata oluştu: {str(e)}")


# Yerel fotoğraf önizlemeleri için statik servis (Test ve yerel kullanım için)
SAMPLE_DIR = os.path.join(BASE_DIR, "data", "sample_photos")
os.makedirs(SAMPLE_DIR, exist_ok=True)
app.mount("/local_photos", StaticFiles(directory=SAMPLE_DIR), name="local_photos")

# Frontend statik dosyalarını bağla
FRONTEND_DIR = os.path.join(PROJECT_ROOT, "frontend")
if os.path.exists(FRONTEND_DIR):
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")

