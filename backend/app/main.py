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

import asyncio
from contextlib import asynccontextmanager

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

# Tekil örnekler (Singletons)
db = Database()
face_engine = FaceEngine()
drive_service = DriveService()

AUTO_SYNC_INTERVAL = int(os.getenv("AUTO_SYNC_INTERVAL", 90))


def perform_incremental_sync(folder_id: str) -> dict:
    """Drive klasörünü kontrol edip yeni fotoğrafları ekler, Drive'dan silinenleri de veritabanından temizler."""
    if not drive_service.is_connected():
        return {"status": "error", "message": "Drive bağlı değil"}

    try:
        images = drive_service.list_images_in_folder(folder_id)
    except Exception as e:
        logger.error(f"Otomatik tarama klasör okuma hatası: {e}")
        return {"status": "error", "message": str(e)}

    current_drive_map = {img["id"]: img for img in images}
    current_drive_ids = set(current_drive_map.keys())

    # 1. Drive'dan silinmiş fotoğrafları veritabanından temizle
    db_drive_ids = set(db.get_all_drive_ids())
    deleted_ids = list(db_drive_ids - current_drive_ids)
    deleted_count = 0
    if deleted_ids:
        deleted_count = db.delete_photos_by_drive_ids(deleted_ids)
        logger.info(f"🗑️ Drive'dan silinen {deleted_count} fotoğraf veritabanından temizlendi.")

    # 2. Yeni yüklenen fotoğrafları yapay zekaya indeksle
    new_indexed = 0
    new_faces = 0

    for drive_id, img in current_drive_map.items():
        if db.photo_exists(drive_id):
            continue

        try:
            filename = img.get("name", "photo.jpg")
            stream = drive_service.download_image_to_memory(drive_id)
            view_url = drive_service.get_direct_view_url(drive_id)
            download_url = drive_service.get_download_url(drive_id)

            photo_id = db.add_photo(
                drive_id=drive_id,
                filename=filename,
                view_url=view_url,
                download_url=download_url,
                mime_type=img.get("mimeType", "image/jpeg")
            )

            faces = face_engine.extract_faces_from_image(stream)
            for face in faces:
                db.add_face(photo_id, face["embedding"], face["box"], face["confidence"])
                new_faces += 1

            new_indexed += 1
            logger.info(f"Arka plan: Yeni fotoğraf indekslendi -> {filename} ({len(faces)} yüz)")
        except Exception as e:
            logger.error(f"Fotoğraf otomatik işlenirken hata ({drive_id}): {e}")

    if new_indexed > 0 or deleted_count > 0:
        logger.info(f"✅ Senkronizasyon tamam: +{new_indexed} yeni, -{deleted_count} silinen, +{new_faces} yüz.")

    return {
        "status": "success", 
        "new_photos": new_indexed, 
        "deleted_photos": deleted_count,
        "new_faces": new_faces
    }


async def background_sync_loop():
    """Belirli aralıklarla arka planda otomatik tarama yapar."""
    while True:
        try:
            await asyncio.sleep(AUTO_SYNC_INTERVAL)
            folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "12ile--MomqOHEuLhOTaFC7lZHm8WSlNBAVCm6A37AgBIC3DdjaTkRtZKz08i4Q5Ke2KfQbY1")
            if folder_id and folder_id != "BURAYA_DRIVE_KLASOR_ID_GELECEK" and drive_service.is_connected():
                await asyncio.to_thread(perform_incremental_sync, folder_id)
        except asyncio.CancelledError:
            logger.info("Arka plan tarayıcısı durduruldu.")
            break
        except Exception as e:
            logger.error(f"Arka plan döngüsünde beklenmeyen hata: {e}")


async def initial_sync_task():
    """Sunucu ayağa kalktıktan 5 saniye sonra ilk senkronizasyonu başlatır."""
    try:
        await asyncio.sleep(5)
        folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "12ile--MomqOHEuLhOTaFC7lZHm8WSlNBAVCm6A37AgBIC3DdjaTkRtZKz08i4Q5Ke2KfQbY1")
        if folder_id and folder_id != "BURAYA_DRIVE_KLASOR_ID_GELECEK" and drive_service.is_connected():
            logger.info("Sunucu başlangıç ilk Drive senkronizasyonu başlatılıyor...")
            await asyncio.to_thread(perform_incremental_sync, folder_id)
    except Exception as e:
        logger.warning(f"İlk senkronizasyonda hata: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    sync_task = None
    init_task = None
    if AUTO_SYNC_INTERVAL > 0:
        sync_task = asyncio.create_task(background_sync_loop())
        logger.info(f"Otomatik Drive tarayıcısı aktif edildi (Her {AUTO_SYNC_INTERVAL} saniyede bir kontrol edilecek).")
    init_task = asyncio.create_task(initial_sync_task())
    yield
    if sync_task:
        sync_task.cancel()
    if init_task:
        init_task.cancel()


app = FastAPI(
    title="Lumina Events API",
    description="Google Drive ve Face Recognition tabanlı akıllı etkinlik fotoğraf servisi",
    version="1.0.0",
    lifespan=lifespan
)

# Mobil cihazların yerel ağdan erişebilmesi için CORS izni
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Tarayıcıların JS/CSS dosyalarını önbelleğe alıp güncellemeleri kaçırmasını engelle (No-Cache)
@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    path = request.url.path
    if path.endswith((".js", ".css", ".html")) or path == "/":
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


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
    stats = db.get_stats()
    stats["auto_sync_interval_seconds"] = AUTO_SYNC_INTERVAL
    stats["auto_sync_interval_minutes"] = max(1, AUTO_SYNC_INTERVAL // 60)
    return stats


@app.post("/api/sync")
async def manual_sync():
    """İsteğe bağlı anlık Drive taramasını manuel olarak tetikler."""
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "12ile--MomqOHEuLhOTaFC7lZHm8WSlNBAVCm6A37AgBIC3DdjaTkRtZKz08i4Q5Ke2KfQbY1")
    if not folder_id or folder_id == "BURAYA_DRIVE_KLASOR_ID_GELECEK":
        raise HTTPException(status_code=400, detail="Google Drive klasör ID ayarlanmamış.")
    result = await asyncio.to_thread(perform_incremental_sync, folder_id)
    return result



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

