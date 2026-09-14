import io
import logging
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import torch
from PIL import Image
from facenet_pytorch import MTCNN, InceptionResnetV1

logger = logging.getLogger(__name__)


class FaceEngine:
    _instance = None

    def __new__(cls, *args, **kwargs):
        """Tek bir model örneğini hafızada tutarak gereksiz RAM tüketimini engeller (Singleton)."""
        if cls._instance is None:
            cls._instance = super(FaceEngine, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self, device: Optional[str] = None):
        if self._initialized:
            return

        # Apple Silicon ARM64 CPU üzerinde son derece hızlı ve MPS havuzlama hatasından arındırılmış kararlı çalışma
        self.device = torch.device('cpu')
        logger.info(f"FaceEngine başlatılıyor... Kullanılan Donanım: {self.device}")

        # MTCNN: Yüz Tespiti (Çoklu yüzler, açılı/yan duruşlar için optimize edilmiş parametreler)
        # keep_all=True sayesinde kalabalık düğün fotoğraflarındaki tüm yüzleri tek seferde yakalar
        self.mtcnn = MTCNN(
            image_size=160,
            margin=14,
            min_face_size=20,
            thresholds=[0.6, 0.7, 0.7],
            factor=0.709,
            post_process=True,
            keep_all=True,
            device=self.device
        )

        # InceptionResnetV1: VGGFace2 üzerinde eğitilmiş 512-D Embedding Modeli
        self.resnet = InceptionResnetV1(pretrained='vggface2').eval().to(self.device)

        self._initialized = True
        logger.info("FaceEngine modelleri hazır.")

    def _load_pil_image(self, image_input) -> Image.Image:
        """Gelen dosya yolunu veya io.BytesIO akışını güvenle RGB PIL Image nesnesine dönüştürür."""
        if isinstance(image_input, Image.Image):
            img = image_input
        elif isinstance(image_input, (io.BytesIO, bytes)):
            if isinstance(image_input, bytes):
                image_input = io.BytesIO(image_input)
            img = Image.open(image_input)
        elif isinstance(image_input, str):
            img = Image.open(image_input)
        else:
            raise ValueError(f"Desteklenmeyen görsel formatı: {type(image_input)}")

        if img.mode != 'RGB':
            img = img.convert('RGB')

        # Bellek ve hız optimizasyonu: Çok devasa görselleri yüz tespitini bozmayacak şekilde sınırla
        max_dim = 1920
        if max(img.size) > max_dim:
            img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

        return img

    def extract_faces_from_image(self, image_input) -> List[Dict[str, Any]]:
        """
        Fotoğraftaki TÜM yüzleri tespit eder ve her birinin 512-boyutlu normalize vektörünü döner.
        Dönüş: [{'embedding': np.ndarray, 'box': [x1, y1, x2, y2], 'confidence': float}, ...]
        """
        img = self._load_pil_image(image_input)

        with torch.no_grad():
            # 1. Yüzleri ve konum kutularını tespit et
            boxes, probs = self.mtcnn.detect(img)

            if boxes is None or len(boxes) == 0:
                return []

            # 2. Yüz piksellerini kırp ve tensöre dönüştür
            faces_tensor = self.mtcnn.extract(img, boxes, save_path=None)
            if faces_tensor is None:
                return []

            if faces_tensor.ndim == 3:
                faces_tensor = faces_tensor.unsqueeze(0)

            faces_tensor = faces_tensor.to(self.device)

            # 3. 512-D embedding vektörlerini hesapla
            embeddings = self.resnet(faces_tensor)
            # L2 Normalizasyonu (Kosinüs benzerliği için kritik)
            embeddings = torch.nn.functional.normalize(embeddings, p=2, dim=1)
            embeddings_np = embeddings.cpu().numpy()

        results = []
        for i in range(len(boxes)):
            prob = float(probs[i]) if probs is not None and probs[i] is not None else 1.0
            if prob < 0.65:  # Düşük güvenilirlikli tespitleri ele
                continue

            results.append({
                "embedding": embeddings_np[i],
                "box": [float(c) for c in boxes[i]],
                "confidence": prob
            })

        return results

    def extract_face_from_selfie(self, image_input) -> Optional[np.ndarray]:
        """
        Davetlinin yüklediği selfie'den TEK BİR ana yüz seçer ve 512-D normalize vektörünü döner.
        Eğer birden fazla yüz varsa en belirgin/büyük olanı seçer.
        """
        faces = self.extract_faces_from_image(image_input)
        if not faces:
            return None

        # En büyük kutu alanına (veya en yüksek güvene) sahip yüzü birincil yüz kabul et
        best_face = max(faces, key=lambda f: (f["box"][2] - f["box"][0]) * (f["box"][3] - f["box"][1]))
        return best_face["embedding"]

    @staticmethod
    def match_faces(
        query_embedding: np.ndarray,
        face_ids: List[int],
        photo_ids: List[int],
        embeddings_matrix: np.ndarray,
        threshold: float = 0.45
    ) -> List[Dict[str, Any]]:
        """
        NumPy matris çarpımı ile 10 milisaniyede tüm veritabanını tarar.
        Kosinüs Mesafesi = 1 - (A . B)
        Mesafe <= threshold ise eşleşme kabul edilir (Mesafe ne kadar küçükse benzerlik o kadar yüksektir).
        """
        if len(face_ids) == 0 or embeddings_matrix.shape[0] == 0:
            return []

        # query vektörünü normalize et
        query_norm = query_embedding / np.linalg.norm(query_embedding)

        # Tek matris çarpımı ile tüm yüzlerle kosinüs benzerliği: (N,)
        similarities = np.dot(embeddings_matrix, query_norm)
        distances = 1.0 - similarities

        # Eşleşenleri bul
        matching_indices = np.where(distances <= threshold)[0]
        if len(matching_indices) == 0:
            return []

        # Fotoğraf bazında grupla (Aynı fotoğrafta birden fazla yüz eşleşirse en iyi skoru al)
        photo_best_match: Dict[int, Dict[str, Any]] = {}

        for idx in matching_indices:
            p_id = photo_ids[idx]
            dist = float(distances[idx])
            sim = float(similarities[idx])
            # Benzerlik yüzdesi (%0 - %100)
            confidence_pct = max(0.0, min(100.0, (1.0 - dist) * 100))

            if p_id not in photo_best_match or dist < photo_best_match[p_id]["distance"]:
                photo_best_match[p_id] = {
                    "photo_id": p_id,
                    "distance": dist,
                    "similarity": sim,
                    "match_score": round(confidence_pct, 1)
                }

        # En iyi eşleşmeden en düşüğe doğru sırala
        ranked_results = sorted(photo_best_match.values(), key=lambda x: x["distance"])
        return ranked_results
