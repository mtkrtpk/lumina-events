#!/bin/bash
# Lumina Events - Tek Tıkla Başlatma ve Canlı Yayına Alma Scripti
cd "$(dirname "$0")"

clear
echo "========================================================"
echo "  ✨ LUMINA EVENTS - İREM & MURATCAN DÜĞÜN PLATFORMU ✨"
echo "========================================================"
echo ""
echo "🚀 1. Sistem ve Yapay Zeka Sunucusu Başlatılıyor..."
echo "☕ 2. Bilgisayarın uykuya geçmesi otomatik engelleniyor..."
echo "🌐 3. Güvenli İnternet Tüneli Açılıyor..."
echo ""
echo "--------------------------------------------------------"
echo "ℹ️  Düğün boyunca bu terminal penceresini açık bırakın."
echo "--------------------------------------------------------"
echo ""

# Mac'in ekran ve sistem uykusuna geçmesini engelle
caffeinate -dimsu &
CAFF_PID=$!

# Sanal ortamı etkinleştir ve sunucuyu başlat
source .venv/bin/activate
uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 &
UVI_PID=$!

# Temiz çıkış için trap fonksiyonu
cleanup() {
    echo ""
    echo "Durduruluyor..."
    kill $UVI_PID 2>/dev/null
    kill $CAFF_PID 2>/dev/null
    exit 0
}
trap cleanup SIGINT SIGTERM EXIT

sleep 2

# Ngrok kalıcı canlı tüneli başlat
echo "🎉 KALICI WEB ADRESİNİZ:"
echo "👉 https://backwash-basics-cogwheel.ngrok-free.dev"
echo ""
./bin/ngrok http --url=backwash-basics-cogwheel.ngrok-free.dev 8000
