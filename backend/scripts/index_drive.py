import os
import sys
import argparse
import logging
from tqdm import tqdm
from dotenv import load_dotenv

# Backend modül yolunu ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.drive_service import DriveService
from app.face_engine import FaceEngine
from app.database import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("indexer")

load_dotenv()


def index_google_drive(folder_id: str, force_reindex: bool = False):
    """Google Drive klasöründeki fotoğrafları RAM üzerinden okuyarak indeksler."""
    print("=" * 65)
    print("🚀 Google Drive Yüz İndeksleme İşlemi Başlatılıyor...")
    print(f"📁 Hedef Drive Klasörü ID: {folder_id}")
    print("=" * 65)

    drive = DriveService()
    if not drive.is_connected():
        print("❌ HATA: Google Drive servisine bağlanılamadı. Lütfen 'backend/credentials/credentials.json' dosyasını kontrol edin.")
        return

    db = Database()
    engine = FaceEngine()

    try:
        images = drive.list_images_in_folder(folder_id)
    except Exception as e:
        print(f"❌ Klasör taranırken hata: {e}")
        return

    if not images:
        print("⚠️ Klasörde indekslenecek fotoğraf bulunamadı.")
        return

    print(f"📸 Toplam {len(images)} fotoğraf bulundu. Yüz analizi başlıyor...\n")

    new_indexed_count = 0
    total_faces_found = 0

    for img_meta in tqdm(images, desc="Fotoğraflar İşleniyor"):
        drive_id = img_meta["id"]
        filename = img_meta.get("name", "photo.jpg")

        # Daha önce indekslenmiş mi kontrol et
        if not force_reindex and db.photo_exists(drive_id):
            continue

        try:
            # 1. Fotoğrafı diske yazmadan doğrudan RAM'e çek
            stream = drive.download_image_to_memory(drive_id)

            # 2. Web önizleme ve indirme linklerini üret
            view_url = drive.get_direct_view_url(drive_id)
            download_url = drive.get_download_url(drive_id)

            # 3. Veritabanına fotoğraf kaydını aç
            photo_id = db.add_photo(
                drive_id=drive_id,
                filename=filename,
                view_url=view_url,
                download_url=download_url,
                mime_type=img_meta.get("mimeType", "image/jpeg")
            )

            # 4. Yüzleri tespit et ve vektörleri çıkar
            faces = engine.extract_faces_from_image(stream)

            # Eski yüzleri temizle ve yenilerini kaydet
            db.delete_faces_of_photo(photo_id)
            for face in faces:
                db.add_face(
                    photo_id=photo_id,
                    embedding=face["embedding"],
                    box=face["box"],
                    confidence=face["confidence"]
                )
                total_faces_found += 1

            new_indexed_count += 1

        except Exception as e:
            logger.error(f"Fotoğraf işlenirken hata ({filename}): {e}")

    stats = db.get_stats()
    print("\n" + "=" * 65)
    print(f"✅ İndeksleme Tamamlandı!")
    print(f"  • Yeni İşlenen Fotoğraf: {new_indexed_count}")
    print(f"  • Tespit Edilen Yeni Yüz : {total_faces_found}")
    print(f"  • Veritabanı Toplam Fotoğraf: {stats['total_photos']}")
    print(f"  • Veritabanı Toplam Yüz     : {stats['total_faces']}")
    print("=" * 65)


def index_local_directory(directory_path: str, force_reindex: bool = False):
    """Yerel testler için belirtilen yerel klasördeki fotoğrafları indeksler."""
    print("=" * 65)
    print(f"📂 Yerel Klasör İndeksleniyor: {directory_path}")
    print("=" * 65)

    if not os.path.exists(directory_path):
        print(f"❌ HATA: '{directory_path}' klasörü bulunamadı.")
        return

    valid_exts = {".jpg", ".jpeg", ".png", ".webp"}
    files = [
        os.path.join(directory_path, f) for f in os.listdir(directory_path)
        if os.path.splitext(f.lower())[1] in valid_exts
    ]

    if not files:
        print("⚠️ Klasörde fotoğraf bulunamadı.")
        return

    db = Database()
    engine = FaceEngine()

    new_indexed_count = 0
    total_faces_found = 0

    for file_path in tqdm(files, desc="Yerel Fotoğraflar"):
        filename = os.path.basename(file_path)
        fake_drive_id = f"local_{filename}"

        if not force_reindex and db.photo_exists(fake_drive_id):
            continue

        try:
            photo_id = db.add_photo(
                drive_id=fake_drive_id,
                filename=filename,
                view_url=f"/local_photos/{filename}",
                download_url=f"/local_photos/{filename}",
                mime_type="image/jpeg"
            )

            faces = engine.extract_faces_from_image(file_path)
            db.delete_faces_of_photo(photo_id)
            for face in faces:
                db.add_face(
                    photo_id=photo_id,
                    embedding=face["embedding"],
                    box=face["box"],
                    confidence=face["confidence"]
                )
                total_faces_found += 1

            new_indexed_count += 1
        except Exception as e:
            logger.error(f"Dosya işlenirken hata ({filename}): {e}")

    stats = db.get_stats()
    print("\n" + "=" * 65)
    print(f"✅ Yerel İndeksleme Tamamlandı!")
    print(f"  • Yeni İşlenen Fotoğraf : {new_indexed_count}")
    print(f"  • Tespit Edilen Yeni Yüz  : {total_faces_found}")
    print(f"  • Veritabanı Toplam Fotoğraf: {stats['total_photos']}")
    print(f"  • Veritabanı Toplam Yüz     : {stats['total_faces']}")
    print("=" * 65)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Düğün & Etkinlik Fotoğraf Yüz İndeksleyici")
    parser.add_argument("--folder-id", type=str, help="Google Drive Klasör ID")
    parser.add_argument("--local-dir", type=str, help="Yerel test klasörü yolu")
    parser.add_argument("--force", action="store_true", help="Daha önce taranmış fotoğrafları zorla tekrar tara")
    args = parser.parse_args()

    if args.local_dir:
        index_local_directory(args.local_dir, force_reindex=args.force)
    else:
        folder_id = args.folder_id or os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        if not folder_id or folder_id == "BURAYA_DRIVE_KLASOR_ID_GELECEK":
            print("❌ HATA: Lütfen bir Google Drive Klasör ID belirtin.")
            print("Kullanım: python index_drive.py --folder-id <KLASOR_ID> veya .env içine GOOGLE_DRIVE_FOLDER_ID yazın.")
            print("Alternatif (Yerel Test): python index_drive.py --local-dir <KLASOR_YOLU>")
            sys.exit(1)
        index_google_drive(folder_id, force_reindex=args.force)
