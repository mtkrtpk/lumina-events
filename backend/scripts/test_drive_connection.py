import os
import sys

# Backend modül yolunu ekle
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app.drive_service import DriveService
from dotenv import load_dotenv

load_dotenv()


def test_connection():
    print("=" * 60)
    print("🔍 Google Drive API Bağlantı Testi")
    print("=" * 60)

    creds_path = os.getenv("GOOGLE_CREDENTIALS_PATH", "backend/credentials/credentials.json")
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID")

    print(f"Kimlik Dosyası Yolu: {creds_path}")
    print(f"Hedef Klasör ID     : {folder_id or 'Henüz .env içinde ayarlanmadı'}")

    if not os.path.exists(creds_path):
        print("\n❌ HATA: 'backend/credentials/credentials.json' dosyası bulunamadı!")
        print("Lütfen Google Cloud Console'dan indirdiğiniz Service Account JSON anahtarını bu konuma kaydedin.")
        return False

    drive = DriveService(credentials_path=creds_path)
    if not drive.is_connected():
        print("\n❌ HATA: Google Drive servisine bağlanılamadı. JSON dosyasını kontrol edin.")
        return False

    print("\n✅ Google Drive API ile başarıyla el sıkışıldı!")

    if not folder_id or folder_id == "BURAYA_DRIVE_KLASOR_ID_GELECEK":
        print("\nℹ️ Klasör listeleme testi için .env dosyasındaki GOOGLE_DRIVE_FOLDER_ID değerini doldurabilirsiniz.")
        return True

    try:
        images = drive.list_images_in_folder(folder_id)
        print(f"✅ Klasör erişimi başarılı! Toplam {len(images)} görsel tespit edildi.")
        if images:
            first = images[0]
            print(f"  Örnek Fotoğraf: {first.get('name')} (ID: {first.get('id')})")
            print(f"  RAM'e akış testi yapılıyor...")
            stream = drive.download_image_to_memory(first['id'])
            print(f"✅ Başarılı! {len(stream.getvalue())} bayt doğrudan RAM'e aktarıldı (diske yazılmadı).")
        return True
    except Exception as e:
        print(f"\n❌ Klasör okunurken hata oluştu: {e}")
        print("İpucu: Drive klasörünü Service Account e-posta adresinizle 'Görüntüleyen' olarak paylaştığınızdan emin olun.")
        return False


if __name__ == "__main__":
    test_connection()
