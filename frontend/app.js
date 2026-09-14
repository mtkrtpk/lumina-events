/**
 * Moments.ai - Frontend Uygulama Mantığı
 */

document.addEventListener("DOMContentLoaded", () => {
  // DOM Elementleri
  const statsText = document.getElementById("statsText");
  const cameraInput = document.getElementById("cameraInput");
  const galleryInput = document.getElementById("galleryInput");
  const btnCamera = document.getElementById("btnCamera");
  const btnGallery = document.getElementById("btnGallery");
  const dropZone = document.getElementById("dropZone");
  const previewZone = document.getElementById("previewZone");
  const previewImage = document.getElementById("previewImage");
  const scanStatusText = document.getElementById("scanStatusText");
  const btnCancelScan = document.getElementById("btnCancelScan");
  
  const heroSection = document.getElementById("heroSection");
  const resultsSection = document.getElementById("resultsSection");
  const resultsSubtitle = document.getElementById("resultsSubtitle");
  const photoGrid = document.getElementById("photoGrid");
  const btnNewSearch = document.getElementById("btnNewSearch");
  
  const emptyState = document.getElementById("emptyState");
  const btnRetry = document.getElementById("btnRetry");
  
  const lightboxModal = document.getElementById("lightboxModal");
  const lightboxImage = document.getElementById("lightboxImage");
  const lightboxScore = document.getElementById("lightboxScore");
  const lightboxDownloadBtn = document.getElementById("lightboxDownloadBtn");
  const lightboxClose = document.getElementById("lightboxClose");
  const lightboxBackdrop = document.getElementById("lightboxBackdrop");
  
  const toast = document.getElementById("toast");

  let currentMatches = [];

  // ==========================================================================
  // 1. İstatistikleri ve Sistem Durumunu Yükle
  // ==========================================================================
  async function loadStats() {
    try {
      const res = await fetch("/api/stats");
      if (!res.ok) throw new Error("Stats alınamadı");
      const data = await res.json();
      const photos = data.total_photos || 0;
      const faces = data.total_faces || 0;

      if (photos > 0) {
        statsText.textContent = `${photos.toLocaleString()} Fotoğraf Hazır`;
      } else {
        statsText.textContent = "Fotoğraflar bekleniyor";
      }
    } catch (e) {
      statsText.textContent = "Sistem Çevrimiçi";
    }
  }

  loadStats();

  // ==========================================================================
  // 1.1 Tek Tıkla Manuel Drive Senkronizasyonu (Sync)
  // ==========================================================================
  const btnSyncAlbum = document.getElementById("btnSyncAlbum");
  const syncIcon = document.getElementById("syncIcon");
  let isSyncing = false;

  async function triggerDriveSync() {
    if (isSyncing) return;
    isSyncing = true;

    syncIcon.classList.add("spinning");
    statsText.textContent = "Drive taranıyor...";
    showToast("🔄 Google Drive taranıyor, yeni fotoğraflar kontrol ediliyor...");

    try {
      const res = await fetch("/api/sync", { method: "POST" });
      const data = await res.json();

      if (data.status === "success") {
        if (data.new_photos > 0) {
          showToast(`✅ Harika! ${data.new_photos} yeni fotoğraf ve ${data.new_faces} yeni yüz eklendi!`);
        } else {
          showToast("✅ Drive güncel! Yeni bir fotoğraf bulunamadı.");
        }
      } else {
        showToast("⚠️ Tarama sırasında uyarı: " + (data.message || "Bilinmeyen durum"));
      }
    } catch (err) {
      console.error("Senkronizasyon hatası:", err);
      showToast("❌ Drive ile iletişim kurulamadı.");
    } finally {
      syncIcon.classList.remove("spinning");
      await loadStats();
      isSyncing = false;
    }
  }

  if (btnSyncAlbum) {
    btnSyncAlbum.addEventListener("click", triggerDriveSync);
  }

  // ==========================================================================
  // 2. Canlı Kamera Kontrolü (WebRTC) ve Dosya Seçimi
  // ==========================================================================
  const cameraModal = document.getElementById("cameraModal");
  const cameraVideo = document.getElementById("cameraVideo");
  const cameraCanvas = document.getElementById("cameraCanvas");
  const btnShutter = document.getElementById("btnShutter");
  const btnCloseCamera = document.getElementById("btnCloseCamera");
  const cameraBackdrop = document.getElementById("cameraBackdrop");

  let mediaStream = null;

  async function startLiveCamera() {
    // Tarayıcı kamera API desteği kontrolü
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      // Desteklenmiyorsa standart dosya seçiciye yönlendir
      cameraInput.click();
      return;
    }

    try {
      mediaStream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: "user",
          width: { ideal: 1280 },
          height: { ideal: 720 }
        },
        audio: false
      });

      cameraVideo.srcObject = mediaStream;
      cameraModal.classList.remove("hidden");
      document.body.style.overflow = "hidden";
    } catch (err) {
      console.warn("Kamera erişimi sağlanamadı, dosya seçiciye yönlendiriliyor:", err);
      showToast("Kamera açılamadı veya izin verilmedi. Dosya seçici açılıyor.");
      cameraInput.click();
    }
  }

  function stopLiveCamera() {
    if (mediaStream) {
      mediaStream.getTracks().forEach(track => track.stop());
      mediaStream = null;
    }
    cameraVideo.srcObject = null;
    cameraModal.classList.add("hidden");
    document.body.style.overflow = "auto";
  }

  function capturePhotoFromCamera() {
    if (!mediaStream) return;

    const width = cameraVideo.videoWidth || 640;
    const height = cameraVideo.videoHeight || 480;

    cameraCanvas.width = width;
    cameraCanvas.height = height;

    const ctx = cameraCanvas.getContext("2d");
    // Aynalanmış görüntüyü düzelt (selfie modu)
    ctx.translate(width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(cameraVideo, 0, 0, width, height);

    cameraCanvas.toBlob((blob) => {
      stopLiveCamera();
      if (blob) {
        const file = new File([blob], "selfie_camera.jpg", { type: "image/jpeg" });
        processFile(file);
      }
    }, "image/jpeg", 0.95);
  }

  btnCamera.addEventListener("click", startLiveCamera);
  btnShutter.addEventListener("click", capturePhotoFromCamera);
  btnCloseCamera.addEventListener("click", stopLiveCamera);
  cameraBackdrop.addEventListener("click", stopLiveCamera);

  btnGallery.addEventListener("click", () => galleryInput.click());

  cameraInput.addEventListener("change", handleFileSelect);
  galleryInput.addEventListener("change", handleFileSelect);

  // Sürükle - Bırak (Drag and Drop)
  uploadCard = document.getElementById("uploadCard");
  uploadCard.addEventListener("dragover", (e) => {
    e.preventDefault();
    uploadCard.style.borderColor = "var(--accent-gold)";
  });

  uploadCard.addEventListener("dragleave", () => {
    uploadCard.style.borderColor = "var(--border-glass)";
  });

  uploadCard.addEventListener("drop", (e) => {
    e.preventDefault();
    uploadCard.style.borderColor = "var(--border-glass)";
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      processFile(e.dataTransfer.files[0]);
    }
  });

  function handleFileSelect(e) {
    if (e.target.files && e.target.files.length > 0) {
      processFile(e.target.files[0]);
    }
  }

  btnCancelScan.addEventListener("click", resetToUpload);
  btnRetry.addEventListener("click", resetToUpload);
  btnNewSearch.addEventListener("click", resetToUpload);

  // ==========================================================================
  // 3. Fotoğrafı İşleme ve API'ye Gönderme
  // ==========================================================================
  async function processFile(file) {
    if (!file.type.startsWith("image/")) {
      showToast("Lütfen geçerli bir görsel dosyası seçin.");
      return;
    }

    // Önizlemeyi göster
    const reader = new FileReader();
    reader.onload = (e) => {
      previewImage.src = e.target.result;
      dropZone.classList.add("hidden");
      previewZone.classList.remove("hidden");
      emptyState.classList.add("hidden");
      scanStatusText.textContent = "Yüz taranıyor ve albüm taranıyor...";
    };
    reader.readAsDataURL(file);

    // API'ye Gönder
    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch("/api/search", {
        method: "POST",
        body: formData
      });

      const data = await response.json();

      if (!response.ok || !data.success) {
        resetToUpload();
        showToast(data.message || data.detail || "Yüz tespit edilemedi. Lütfen net bir fotoğraf yükleyin.");
        return;
      }

      // Başarılı Arama
      if (data.total_matches > 0) {
        currentMatches = data.matches;
        renderResults(data);
      } else {
        showEmptyState();
      }

    } catch (err) {
      console.error("Arama hatası:", err);
      resetToUpload();
      showToast("Sunucu ile bağlantı kurulamadı. Lütfen tekrar deneyin.");
    }
  }

  // ==========================================================================
  // 4. Sonuçları Ekrana Basma (Galeri Grid)
  // ==========================================================================
  function renderResults(data) {
    previewZone.classList.add("hidden");
    heroSection.classList.add("hidden");
    resultsSection.classList.remove("hidden");
    emptyState.classList.add("hidden");

    resultsSubtitle.textContent = `${data.total_matches} karede seni bulduk (${data.execution_time_ms} ms)`;
    photoGrid.innerHTML = "";

    data.matches.forEach((item, index) => {
      const card = document.createElement("div");
      card.className = "photo-card";
      card.innerHTML = `
        <div class="photo-img-wrapper" data-index="${index}">
          <span class="match-badge">%${item.match_score} Eşleşme</span>
          <img src="${item.view_url}" alt="${item.filename}" loading="lazy" onerror="this.src='data:image/svg+xml;utf8,<svg xmlns=\\'http://www.w3.org/2000/svg\\' width=\\'200\\' height=\\'200\\' fill=\\'%23222\\'><rect width=\\'200\\' height=\\'200\\'/><text x=\\'50%\\' y=\\'50%\\' fill=\\'%23666\\' dominant-baseline=\\'middle\\' text-anchor=\\'middle\\'>Fotoğraf</text></svg>'">
        </div>
        <div class="photo-card-footer">
          <span class="photo-name" title="${item.filename}">${item.filename}</span>
          <a href="${item.download_url}" target="_blank" download="${item.filename}" class="btn-download-icon" title="Orijinal Boyutta İndir">
            ⬇️ İndir
          </a>
        </div>
      `;

      // Kart tıklamasında Lightbox aç
      const imgWrapper = card.querySelector(".photo-img-wrapper");
      imgWrapper.addEventListener("click", () => openLightbox(index));

      photoGrid.appendChild(card);
    });

    // Sonuçlara yumuşak kaydır
    window.scrollTo({ top: resultsSection.offsetTop - 80, behavior: "smooth" });
  }

  function showEmptyState() {
    previewZone.classList.add("hidden");
    emptyState.classList.remove("hidden");
  }

  function resetToUpload() {
    cameraInput.value = "";
    galleryInput.value = "";
    previewZone.classList.add("hidden");
    dropZone.classList.remove("hidden");
    resultsSection.classList.add("hidden");
    emptyState.classList.add("hidden");
    heroSection.classList.remove("hidden");
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  // ==========================================================================
  // 5. Tam Ekran Lightbox (Modal)
  // ==========================================================================
  function openLightbox(index) {
    const item = currentMatches[index];
    if (!item) return;

    lightboxImage.src = item.view_url;
    lightboxScore.textContent = `%${item.match_score} Eşleşme`;
    lightboxDownloadBtn.href = item.download_url;
    lightboxDownloadBtn.setAttribute("download", item.filename);

    lightboxModal.classList.remove("hidden");
    document.body.style.overflow = "hidden";
  }

  function closeLightbox() {
    lightboxModal.classList.add("hidden");
    document.body.style.overflow = "auto";
  }

  lightboxClose.addEventListener("click", closeLightbox);
  lightboxBackdrop.addEventListener("click", closeLightbox);

  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !lightboxModal.classList.contains("hidden")) {
      closeLightbox();
    }
  });

  // ==========================================================================
  // 6. Toast Bildirimi Yardımcısı
  // ==========================================================================
  let toastTimer = null;
  function showToast(message) {
    toast.textContent = message;
    toast.classList.remove("hidden");

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      toast.classList.add("hidden");
    }, 4000);
  }
});
