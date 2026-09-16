# Python 3.11 tabanlı hafif ve kararlı Linux imajı
FROM python:3.11-slim

# Gerekli sistem kütüphaneleri (OpenCV, GLib vb.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Hugging Face Spaces için standart kullanıcı (UID 1000)
RUN useradd -m -u 1000 user
USER user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR $HOME/app

# Bağımlılıkları kopyala ve kur (CPU optimize PyTorch ile hızlı kurulum)
COPY --chown=user:user backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

# Proje dosyalarını kopyala
COPY --chown=user:user . $HOME/app

# Veritabanı ve veri klasörünün izinlerini hazırla
RUN mkdir -p $HOME/app/backend/data && chmod 777 $HOME/app/backend/data

# Hugging Face Spaces standart portu: 7860 (veya dinamik PORT)
ENV PORT=7860
EXPOSE 7860

# FastAPI Uvicorn sunucusunu başlat
CMD ["sh", "-c", "uvicorn backend.app.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
