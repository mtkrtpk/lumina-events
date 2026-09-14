import io
import os
import logging
from typing import List, Dict, Any, Optional
from google.oauth2 import service_account
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build, Resource
from googleapiclient.http import MediaIoBaseDownload
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# Sadece okuma yetkisi (Yetkileri minimumda tutarak güvenlik sağlıyoruz)
SCOPES = ['https://www.googleapis.com/auth/drive.readonly']


class DriveService:
    def __init__(self, credentials_path: Optional[str] = None):
        """
        Google Drive API Servis Yöneticisi.
        Hem Service Account (Hizmet Hesabı) hem de OAuth 2.0 kimlik doğrulamasını destekler.
        """
        self.credentials_path = credentials_path or os.getenv(
            "GOOGLE_CREDENTIALS_PATH", "backend/credentials/credentials.json"
        )
        self.token_path = os.getenv("GOOGLE_TOKEN_PATH", "backend/credentials/token.json")
        self.service: Optional[Resource] = None
        self._authenticate()

    def _authenticate(self) -> None:
        """
        Drive API kimlik doğrulamasını gerçekleştirir.
        Önce Service Account dosyasını kontrol eder, yoksa OAuth token araması yapar.
        """
        if not os.path.exists(self.credentials_path):
            logger.warning(f"Credentials dosyası bulunamadı: {self.credentials_path}")
            return

        try:
            # 1. Öncelik: Service Account (Sunucu & Otomasyon için en kolayı)
            creds = service_account.Credentials.from_service_account_file(
                self.credentials_path, scopes=SCOPES
            )
            self.service = build('drive', 'v3', credentials=creds)
            logger.info("Google Drive API: Service Account ile başarıyla yetkilendirildi.")
        except Exception as e:
            logger.info(f"Service account denendi, OAuth deneniyor... ({e})")
            # 2. Alternatif: Standart OAuth 2.0
            creds = None
            if os.path.exists(self.token_path):
                creds = Credentials.from_authorized_user_file(self.token_path, SCOPES)
            if not creds or not creds.valid:
                if creds and creds.expired and creds.refresh_token:
                    creds.refresh(Request())
                else:
                    flow = InstalledAppFlow.from_client_secrets_file(self.credentials_path, SCOPES)
                    creds = flow.run_local_server(port=0)
                with open(self.token_path, 'w') as token:
                    token.write(creds.to_json())
            self.service = build('drive', 'v3', credentials=creds)
            logger.info("Google Drive API: OAuth 2.0 ile başarıyla yetkilendirildi.")

    def is_connected(self) -> bool:
        """API bağlantısının hazır olup olmadığını kontrol eder."""
        return self.service is not None

    def list_images_in_folder(self, folder_id: str) -> List[Dict[str, Any]]:
        """
        Belirtilen Drive klasöründeki tüm görsel dosyalarını (JPEG, PNG, HEIC vb.) listeler.
        Tüm sayfalama (pagination) adımlarını otomatik olarak tamamlar.
        """
        if not self.service:
            raise RuntimeError("Drive servisi bağlı değil. Lütfen credentials.json dosyasını kontrol edin.")

        query = f"'{folder_id}' in parents and mimeType contains 'image/' and trashed = false"
        images = []
        page_token = None

        logger.info(f"Drive klasörü taranıyor: {folder_id}")

        while True:
            response = self.service.files().list(
                q=query,
                spaces='drive',
                fields='nextPageToken, files(id, name, mimeType, thumbnailLink, webViewLink, webContentLink)',
                pageToken=page_token,
                pageSize=100
            ).execute()

            files = response.get('files', [])
            images.extend(files)

            page_token = response.get('nextPageToken')
            if not page_token:
                break

        logger.info(f"Toplam {len(images)} adet fotoğraf bulundu.")
        return images

    def download_image_to_memory(self, file_id: str) -> io.BytesIO:
        """
        Fotoğrafı sabit diske KAYDETMEDEN, doğrudan RAM'de (in-memory) io.BytesIO akışına indirir.
        """
        if not self.service:
            raise RuntimeError("Drive servisi bağlı değil.")

        request = self.service.files().get_media(fileId=file_id)
        file_stream = io.BytesIO()
        downloader = MediaIoBaseDownload(file_stream, request, chunksize=1024 * 1024)

        done = False
        while not done:
            status, done = downloader.next_chunk()

        file_stream.seek(0)
        return file_stream

    @staticmethod
    def get_direct_view_url(file_id: str) -> str:
        """
        Web arayüzünde hızlı gösterim için Google CDN formatında doğrudan görsel bağlantısı üretir.
        """
        return f"https://lh3.googleusercontent.com/d/{file_id}"

    @staticmethod
    def get_download_url(file_id: str) -> str:
        """
        Davetlinin fotoğrafı tam kalitede indirebilmesi için indirme bağlantısı üretir.
        """
        return f"https://drive.google.com/uc?export=download&id={file_id}"
