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

Yang dinilai lomba adalah alur **unggah klip** di atas. Batasannya:

- ❌ Tidak ada login / akun pengguna
- ❌ Tidak ada riwayat analisis
- ❌ Tidak ada background job / queue
- ✅ Proses sinkron — satu video pada satu waktu
- ✅ Disarankan klip ≤ 2 menit untuk respons yang nyaman

Streaming CCTV real-time **sudah ada** sebagai mode terpisah dan dimatikan secara
default — lihat bagian berikut.

---

## Mode Produksi CCTV (opsional)

Selain MVP unggah-klip, repo ini berisi lapisan deployment untuk menjalankan SAPA
sebagai perangkat lunak CCTV 24/7: ingest RTSP multi-kamera, alert langsung ke staf,
dan log kejadian dengan retensi otomatis.

**Mode ini nonaktif secara default** agar perilaku submission lomba tidak berubah.
Aktifkan dengan satu env var:

```bash
cp backend/data/cameras.example.json backend/data/cameras.json
# edit cameras.json → isi URL RTSP dan jenis tiap kamera

SAPA_PRODUKSI=1 uvicorn app:app --port 8000
```

Lalu buka **http://localhost:5173/dashboard** untuk dashboard operator, atau
periksa langsung lewat API:
```bash
curl localhost:8000/produksi/kesehatan     # status tiap kamera
curl localhost:8000/produksi/kejadian      # log kejadian
```

**Inti AI-nya tidak dibangun ulang.** Lapisan ini memakai `pipeline/` yang sama
persis dengan mode unggah — bobot, normalisasi, dan ambang yang identik. Yang
ditambahkan murni infrastruktur.

📄 Panduan lengkap (pemasangan kamera, kalibrasi, privasi, kebutuhan hardware):
**[docs/PRODUKSI.md](docs/PRODUKSI.md)**

> ⚠️ Endpoint `/produksi/*` **tidak punya autentikasi**. Untuk pemasangan
> nyata, taruh di balik reverse proxy ber-auth di jaringan toko — jangan pernah
> diekspos langsung ke internet.

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
│   ├── production/              # mode CCTV 24/7 (opsional, SAPA_PRODUKSI=1)
│   │   ├── profiles.py          # profil kamera: jenis → fitur mana yang aktif
│   │   ├── stream.py            # ingest RTSP, reconnect otomatis, drop frame
│   │   ├── buffer.py            # jendela geser per-orang berbasis waktu
│   │   ├── worker.py            # 1 thread/kamera: pose+track → inferensi → alert
│   │   ├── alerts.py            # debounce + log kejadian + retensi
│   │   ├── manager.py           # multi-kamera + pengawas & auto-restart
│   │   └── api.py               # REST /api/produksi/* + WS /ws/produksi/alert
│   ├── tests/                   # uji logika produksi (tanpa kamera/GPU)
│   ├── data/                    # cameras.json + kejadian.jsonl (tidak di-commit)
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

## ⚠️ Kesesuaian dengan Kode Training

Sudah diverifikasi terhadap `Train_fall.ipynb` dan `Kepala Interaksi.ipynb`:

| Hal | Status |
|---|---|
| Agregasi temporal (`out.mean(dim=1)`) | ✅ identik — dikunci `tests/uji_arsitektur.py` |
| 12 sendi (5–16) × x,y untuk Kepala Jatuh | ✅ identik |
| 17 sendi × x,y,conf untuk Kepala Interaksi | ✅ identik |
| `inspect_idx = [4, 5]` | ✅ diambil dari config model |
| `normalize_pose` / `resample_fps` / `make_windows` | ✅ sesuai `Inference.ipynb` |

**Pernah salah, sudah diperbaiki:** `BiLSTMHead.forward()` memakai hidden state
terakhir padahal training memakai mean-pooling. Keduanya memakai parameter yang
sama persis sehingga `load_state_dict(strict=True)` tetap lolos tanpa error —
tapi pada bobot `fall_head` kedua varian hanya sepakat **46%** dari waktu.
Pelajarannya: **model berhasil dimuat bukan bukti forward-pass sudah benar.**

Verifikasi ulang kapan saja:
```bash
cd backend && python tests/uji_arsitektur.py
```

### 🔧 Ambang perlu disetel ulang

Ambang `fall_thr = 0.80` dan `fall_angle` di `app.py` disetel **terhadap
forward-pass yang salah**. Setelah perbaikan, sebaran probabilitas bergeser
turun — pada uji sintetis, jendela yang melewati `fall_thr = 0.80` berkurang
dari 143 menjadi 17 per 2000. Jalankan ulang klip uji dan setel ulang ambangnya
sebelum submission final.

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
