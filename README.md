---
title: Lumina Events - Irem & Muratcan
emoji: 💍
colorFrom: green
colorTo: yellow
sdk: docker
app_port: 7860
pinned: false
---

# 📸 Lumina Events - AI Düğün Fotoğraf Paylaşım Platformu

0 maliyetli (Zero-Cost MVP), davetlilerin Google Drive üzerindeki binlerce fotoğraf arasından sadece kendi yüzlerinin olduğu fotoğrafları saniyeler içinde bulup indirebilmelerini sağlayan hibrit web platformu.

---

## 🏗️ Mimari ve Çalışma Akışı

```
[Davetliler] ──(Google Form)──> [Google Drive Klasörü]
                                       │
                                       ▼ (RAM / Stream)
                            [Yüz İndeksleme Script'i]
                            (face_recognition / dlib)
                                       │
                                       ▼ (128-D Vektörler)
                            [SQLite / face_index.db]
                                       │
[Davetli Selfie] ──> [FastAPI: /api/search] ──> [Eşleşen Fotoğraflar]
                                       │
                                       ▼
                       [Mobil Uyumlu Galeri Arayüzü]
```

1. **Veri Toplama:** Davetliler düğün/etkinlik esnasında veya sonrasında fotoğrafları Google Form ile etkinlik sahibinin Google Drive klasörüne yükler.
2. **Arka Plan İndeksleme:** `python backend/scripts/index_drive.py` script'i Drive'daki fotoğrafları RAM üzerinden okur, yüzleri tespit eder, 128 boyutlu embedding vektörlerini çıkarır ve `backend/data/face_index.db` veritabanına işler.
3. **Arama ve Eşleşme:** Misafir web arayüzünde selfie çeker veya yükler. FastAPI sunucusu kosinüs benzerliği ile eşleşen fotoğrafları bulur.
4. **Hızlı Önizleme & İndirme:** Sonuçlar doğrudan Google CDN önizleme linkleri ile mobil galeride listelenir ve orijinal kalitede indirilebilir.

---

## 📁 Proje Yapısı

```
faturalar/
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI uygulaması ve uç noktalar
│   │   ├── face_engine.py      # Yüz tanıma & vektör karşılaştırma motoru
│   │   ├── drive_service.py    # Google Drive API entegrasyonu
│   │   └── database.py         # SQLite veritabanı yönetimi
│   ├── scripts/
│   │   └── index_drive.py      # Fotoğrafları tarayıp indeksleyen script
│   ├── credentials/            # Google Cloud kimlik dosyaları (.gitignore)
│   ├── data/
│   │   └── face_index.db       # Yüz vektörleri SQLite veritabanı
│   └── requirements.txt        # Python bağımlılıkları
├── frontend/
│   ├── index.html              # Modern, mobil uyumlu kullanıcı arayüzü
│   ├── style.css               # Şık, cam efektli (glassmorphism) stil
│   └── app.js                  # Kamera kontrolü, API istekleri ve galeri yönetimi
├── .env.example
├── .gitignore
└── README.md
```
