# SAPA — Safety and Assistance through Pose Analytics

> **"Melihat Kebutuhan, Bukan Wajah."**

Sistem analitik toko berbasis CCTV yang mendeteksi pelanggan yang **tampak butuh bantuan** dan kejadian **jatuh** — hanya dari pose/kerangka gerak tubuh (koordinat sendi), **bukan wajah, bukan identitas** (privacy-by-design).

Proyek untuk lomba **AI Innovation Challenge COMPFEST 18**.

---

## Cara Menjalankan (Docker Compose)

### Prasyarat
- [Docker Desktop](https://www.docker.com/products/docker-desktop) terinstal dan berjalan
- File bobot model dari tim (lihat bagian **Menyiapkan Bobot Model** di bawah)

### 1. Clone / unduh repo
```bash
git clone <url-repo> sapa
cd sapa
```

### 2. Siapkan bobot model

Taruh 4 file berikut ke folder `backend/models/`:

```
backend/models/
├── fall_head.pt             ← bobot Kepala Jatuh (dari tim)
├── fall_head.json           ← config Kepala Jatuh (sudah tersedia di repo)
├── interaction_head.pt      ← bobot Kepala Interaksi (dari tim)
└── interaction_head.json    ← config Kepala Interaksi (sudah tersedia di repo)
```

> **Catatan:** `yolov8n-pose.pt` akan **otomatis diunduh** oleh `ultralytics` saat pertama kali server dijalankan. Pastikan koneksi internet tersedia saat pertama build/run.

Jika file `.pt` belum tersedia, sistem tetap bisa berjalan dalam **mode stub** — YOLO tetap mengekstrak pose, tapi hasil klasifikasi acak (tidak bermakna). Mode ini berguna untuk pengujian UI.

### 3. Jalankan

```bash
docker compose up --build
```

Tunggu hingga log backend menampilkan:
```
✅ Fall model berhasil dimuat.
✅ Interaction model berhasil dimuat.
INFO:     Application startup complete.
```

Buka browser: **http://localhost:5173**

---

## Cara Pakai

1. **Unggah klip video** (.mp4) via drag-and-drop atau klik tombol pilih file
2. **Pilih jenis kamera:**
   - 🏃 **Kamera Lorong** — kamera samping/depan, aktifkan deteksi jatuh
   - 🛒 **Kamera Rak (Atas)** — kamera top-down menghadap rak, aktifkan deteksi pelayanan
   - ⚙️ **Semua Fitur** — aktifkan keduanya (default)
3. Klik **"Analisis Sekarang"** — proses berjalan di server (sinkron)
4. Lihat **video beranotasi** + **timeline kejadian**
5. Klik item timeline untuk **melompat ke waktu kejadian** di video

---

## Catatan Sudut Kamera (Penting!)

| Jenis Kamera | Cocok Untuk | Tidak Cocok Untuk |
|---|---|---|
| Kamera lorong / samping | ✅ Deteksi jatuh | ❌ Deteksi interaksi rak |
| Kamera rak / top-down | ✅ Deteksi pelayanan | ❌ Deteksi jatuh |

**Kenapa?** Dari sudut tepat atas (top-down), pose berdiri dan pose berbaring sulit dibedakan oleh model yang dilatih dari kamera samping (NTU RGB+D). Gunakan flag jenis kamera yang sesuai untuk menghindari false-positive.

---

## Batasan MVP

- ❌ Tidak ada login / akun pengguna
- ❌ Tidak ada riwayat analisis
- ❌ Tidak ada streaming real-time CCTV
- ❌ Tidak ada background job / queue
- ✅ Proses sinkron — satu video pada satu waktu
- ✅ Disarankan klip ≤ 2 menit untuk respons yang nyaman

---

## Arsitektur Sistem

```
Browser (React/Vite @ :5173)
    │  multipart POST /api/analyze
    ▼
nginx (port 5173, Docker)
    │  reverse proxy /api → backend:8000
    ▼
FastAPI (port 8000, Docker)
    │
    ├─ YOLOv8n-pose  ──→  ekstraksi 17 titik sendi COCO per frame + tracking
    ├─ normalize.py  ──→  normalisasi pose (origin=hip, skala=torso)
    ├─ BiLSTM Fall   ──→  {normal, oleng, jatuh} per jendela 3 detik
    ├─ BiLSTM Inter  ──→  {background, reach, retract, hand_in_shelf, inspect_product, inspect_shelf}
    ├─ geometry.py   ──→  konfirmasi jatuh (sudut torso ≥ 55°) + deteksi diam
    └─ render.py     ──→  video beranotasi (kerangka + label + banner kejadian)
```

---

## Struktur Folder

```
sapa/
├── docker-compose.yml
├── README.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── app.py                   # FastAPI: POST /analyze, GET /outputs
│   ├── pipeline/
│   │   ├── models.py            # BiLSTMHead + load_head() + predict_proba()
│   │   ├── normalize.py         # normalize_pose / resample_fps / make_windows
│   │   ├── geometry.py          # torso_angle / is_dwell / detect helpers
│   │   ├── extract.py           # YOLOv8 tracking → sekuens per orang
│   │   ├── analyze.py           # analyze() → timeline + frame_annotations
│   │   └── render.py            # render() → video beranotasi (OpenCV + ffmpeg)
│   ├── models/                  # .pt + .json (taruh di sini)
│   └── outputs/                 # video beranotasi hasil (auto-dibuat)
├── frontend/
│   ├── Dockerfile
│   ├── nginx.conf
│   ├── package.json
│   ├── vite.config.js
│   ├── index.html
│   └── src/
│       ├── App.jsx
│       ├── components/
│       │   ├── UploadPage.jsx
│       │   ├── ProcessingPage.jsx
│       │   └── ResultPage.jsx
│       └── styles/global.css
└── training/                    # kode training (konteks saja, tidak dijalankan di web)
```

---

## Development Lokal (tanpa Docker)

**Backend:**
```bash
cd backend
pip install -r requirements.txt
uvicorn app:app --reload --port 8000
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev        # buka http://localhost:5173
```

> Pastikan backend berjalan di port 8000 saat development — Vite otomatis proxy `/api/*` ke `http://localhost:8000`.

---

## ⚠️ Catatan Normalisasi (untuk tim training)

File `pipeline/normalize.py` ditulis berdasarkan deskripsi spesifikasi, **belum diverifikasi** terhadap kode training asli. **Sebelum submission final**, lakukan diff antara:
- `normalize_pose()` di web ↔ versi di script training
- `resample_fps()` di web ↔ versi di script training
- `make_windows()` di web ↔ versi di script training

Jika berbeda, model akan memberikan hasil yang tidak bermakna (silent failure — tidak error, tapi prediksi ngawur).

---

## Konvensi Commit

Proyek mengikuti **conventional commits**:
```
feat: tambah fitur baru
fix:  perbaiki bug
refactor: refactor kode tanpa mengubah perilaku
docs: perbarui dokumentasi
chore: perubahan build/config
```

---

*SAPA — AI menandai, manusia memutuskan.*
