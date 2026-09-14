import sqlite3
import os
import json
import logging
import numpy as np
from typing import List, Dict, Any, Tuple, Optional
from datetime import datetime

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DATABASE_PATH", "backend/data/face_index.db")


class Database:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.init_db()

    def get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        """Tabloları ve indeksleri oluşturur."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Fotoğraflar tablosu
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS photos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    drive_id TEXT UNIQUE NOT NULL,
                    filename TEXT NOT NULL,
                    view_url TEXT NOT NULL,
                    download_url TEXT NOT NULL,
                    mime_type TEXT,
                    indexed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            # Yüzler tablosu (vektörler BLOB formatında 512 float32 olarak saklanır)
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS faces (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    photo_id INTEGER NOT NULL,
                    embedding BLOB NOT NULL,
                    box_json TEXT,
                    confidence REAL,
                    FOREIGN KEY (photo_id) REFERENCES photos (id) ON DELETE CASCADE
                );
            """)
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_photos_drive_id ON photos(drive_id);")
            cursor.execute("CREATE INDEX IF NOT EXISTS idx_faces_photo_id ON faces(photo_id);")
            conn.commit()
            logger.info("SQLite veritabanı başarıyla başlatıldı.")

    def photo_exists(self, drive_id: str) -> bool:
        """Fotoğrafın daha önce indekslenip indekslenmediğini kontrol eder."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM photos WHERE drive_id = ?", (drive_id,))
            return cursor.fetchone() is not None

    def add_photo(self, drive_id: str, filename: str, view_url: str, download_url: str, mime_type: str = "") -> int:
        """Yeni bir fotoğraf ekler veya varsa mevcut olanın id'sini döner."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO photos (drive_id, filename, view_url, download_url, mime_type, indexed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(drive_id) DO UPDATE SET
                    view_url=excluded.view_url,
                    download_url=excluded.download_url
            """, (drive_id, filename, view_url, download_url, mime_type, datetime.utcnow()))
            cursor.execute("SELECT id FROM photos WHERE drive_id = ?", (drive_id,))
            photo_id = cursor.fetchone()[0]
            conn.commit()
            return photo_id

    def add_face(self, photo_id: int, embedding: np.ndarray, box: Optional[List[float]] = None, confidence: float = 1.0) -> int:
        """Fotoğrafta tespit edilen bir yüzün 512-D vektörünü BLOB olarak kaydeder."""
        emb_bytes = embedding.astype(np.float32).tobytes()
        box_json = json.dumps(box) if box is not None else None

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO faces (photo_id, embedding, box_json, confidence)
                VALUES (?, ?, ?, ?)
            """, (photo_id, emb_bytes, box_json, confidence))
            face_id = cursor.lastrowid
            conn.commit()
            return face_id

    def delete_faces_of_photo(self, photo_id: int) -> None:
        """Bir fotoğrafın eski yüz kayıtlarını siler (yeniden indeksleme durumunda)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM faces WHERE photo_id = ?", (photo_id,))
            conn.commit()

    def get_all_faces(self) -> Tuple[List[int], List[int], np.ndarray]:
        """
        Tüm kayıtlı yüz vektörlerini tek bir NumPy matrisi olarak döner.
        Dönüş: (face_ids, photo_ids, embeddings_matrix)
        """
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, photo_id, embedding FROM faces")
            rows = cursor.fetchall()

            if not rows:
                return [], [], np.empty((0, 512), dtype=np.float32)

            face_ids = []
            photo_ids = []
            embeddings_list = []

            for row in rows:
                face_ids.append(row["id"])
                photo_ids.append(row["photo_id"])
                emb = np.frombuffer(row["embedding"], dtype=np.float32)
                embeddings_list.append(emb)

            embeddings_matrix = np.vstack(embeddings_list)
            return face_ids, photo_ids, embeddings_matrix

    def get_photos_by_ids(self, photo_ids: List[int]) -> List[Dict[str, Any]]:
        """ID listesine göre fotoğraf detaylarını döner."""
        if not photo_ids:
            return []

        placeholders = ",".join("?" for _ in photo_ids)
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(f"""
                SELECT id, drive_id, filename, view_url, download_url, mime_type, indexed_at
                FROM photos
                WHERE id IN ({placeholders})
            """, photo_ids)
            rows = cursor.fetchall()

            result_map = {row["id"]: dict(row) for row in rows}
            # Orijinal sıralamayı koru
            return [result_map[pid] for pid in photo_ids if pid in result_map]

    def get_stats(self) -> Dict[str, int]:
        """Veritabanındaki fotoğraf ve yüz sayılarını döner."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM photos")
            total_photos = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM faces")
            total_faces = cursor.fetchone()[0]
            return {"total_photos": total_photos, "total_faces": total_faces}

    def clear_all(self) -> None:
        """Tüm kayıtları sıfırlar."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM faces;")
            cursor.execute("DELETE FROM photos;")
            conn.commit()
