# ── Backend Dockerfile — SAPA ──────────────────────────────────────────────
FROM python:3.11-slim

WORKDIR /app

# Dependensi sistem untuk OpenCV + ffmpeg (re-encode H.264)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl \
        libgl1 \
        libglib2.0-0 \
        libsm6 \
        libxext6 \
        libxrender1 \
        ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Install dependensi Python (cache layer terpisah)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Salin kode aplikasi
COPY . .

# Buat direktori output & upload
RUN mkdir -p outputs uploads

EXPOSE 8000

# Jalankan dengan uvicorn (sinkron, 1 worker — sesuai batasan MVP)
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
