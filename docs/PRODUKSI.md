# SAPA — Panduan Deployment CCTV Produksi

> **"AI menandai, manusia memutuskan."**
> Dokumen ini untuk memasang SAPA sebagai perangkat lunak CCTV 24/7 di toko nyata.
> Untuk alur lomba (unggah klip), lihat [README utama](../README.md).

---

## 1. Apa yang baru dibanding MVP

| | MVP (lomba) | Produksi (dokumen ini) |
|---|---|---|
| Masukan | unggah klip `.mp4` | stream RTSP, banyak kamera |
| Proses | sinkron, sekali jalan | kontinu, 24/7 |
| Keluaran | timeline + video beranotasi | alert langsung + log kejadian |
| Model | **sama** | **sama, tanpa perubahan** |

**Inti AI tidak dibangun ulang.** Bobot, normalisasi, dan lapisan geometri yang
dipakai identik dengan mode unggah — modul `production/` memanggil `pipeline/`
apa adanya. Yang ditambahkan murni infrastruktur: ingest stream, buffer real-time,
mesin alert, manajemen multi-kamera, dan operasional.

---

## 2. Menjalankan

```bash
cd backend
cp data/cameras.example.json data/cameras.json
# edit data/cameras.json — isi URL RTSP dan `jenis` tiap kamera

SAPA_PRODUKSI=1 uvicorn app:app --port 8000
```

### Variabel lingkungan

| Variabel | Default | Keterangan |
|---|---|---|
| `SAPA_PRODUKSI` | `0` | `1` untuk menyalakan mode produksi |
| `SAPA_PROFIL_KAMERA` | `data/cameras.json` | lokasi berkas profil kamera |
| `SAPA_LOG_KEJADIAN` | `data/kejadian.jsonl` | lokasi log kejadian |
| `SAPA_RETENSI_JAM` | `72` | masa simpan kejadian sebelum dihapus otomatis |

Cek berhasil atau tidak:
```bash
curl localhost:8000/produksi/kesehatan | python3 -m json.tool
```

### ⚠️ Dua bentuk URL — jangan tertukar

Backend menyajikan endpoint di bawah `/produksi`, mengikuti konvensi endpoint
lain (`/analyze`, `/health`) yang juga tanpa `/api`. Prefiks `/api` adalah
konvensi sisi frontend — nginx dan proxy dev Vite membuangnya sebelum
meneruskan ke backend.

| Dari mana | URL |
|---|---|
| `curl` langsung ke backend | `http://localhost:8000/produksi/kamera` |
| Browser / dashboard | `http://localhost:5173/api/produksi/kamera` |
| WebSocket dari browser | `ws://localhost:5173/api/ws/produksi/alert` |

### Dashboard operator

Buka **http://localhost:5173/dashboard** setelah frontend berjalan
(`cd frontend && npm run dev`).

---

## 3. ⚠️ Sudut kamera menentukan fitur — ini bagian paling mudah salah

Setiap kamera **wajib** diberi `jenis` yang benar:

| `jenis` | Pasang di | Fitur aktif | Fitur mati |
|---|---|---|---|
| `lorong` | samping / miring, menghadap lorong | **Deteksi jatuh** | interaksi |
| `rak` | tepat di atas rak, menghadap ke bawah | **Deteksi butuh bantuan** | jatuh |

**Kenapa dipisah?** Dari sudut tepat-atas, orang berdiri dan orang berbaring
menghasilkan pose yang nyaris identik, dan sudut torso terbaca ≈90° secara
permanen — Kepala Jatuh akan menyala terus-menerus. Sebaliknya, deteksi interaksi
rak butuh pandangan ke area rak yang hanya didapat dari atas.

Ini **ditegakkan oleh kode**, bukan sekadar anjuran: `profiles.py` menurunkan
`run_fall`/`run_interaction` dari `jenis`, sehingga tidak ada cara mengaktifkan
deteksi jatuh pada kamera `rak` lewat konfigurasi.

Toko nyata biasanya butuh keduanya — pasang beberapa kamera lorong **dan**
beberapa kamera rak, lalu SAPA memetakan fitur ke kamera yang tepat.

---

## 4. Profil kamera

Field yang biasanya perlu disetel. Sisanya punya default sesuai `jenis`.

```jsonc
{
  "id": "lorong-1",                 // unik, dipakai di API dan log
  "nama": "Lorong 1 — Minuman",     // muncul di alert yang dibaca staf
  "lokasi": "Sisi timur",
  "sumber": "rtsp://user:pass@192.168.1.11:554/Streaming/Channels/101",
  "jenis": "lorong",                // "lorong" | "rak"  ← lihat bagian 3
  "aktif": true,                    // ikut menyala saat sistem start
  "process_fps": 8.0,               // frame/detik yang diinferensi
  "preview": "kerangka"             // "kerangka" | "video" | "mati"
}
```

`sumber` juga menerima `"0"` (webcam lokal) atau path berkas video. Berkas
berguna untuk demo tanpa kamera fisik — diputar ulang otomatis dengan kecepatan
aslinya, sehingga perilakunya menyerupai stream sungguhan.

### Ambang yang bisa disetel

| Field | Default lorong | Default rak | Fungsi |
|---|---|---|---|
| `fall_thr` | `0.80` | — | ambang probabilitas kelas "jatuh" |
| `fall_angle` | `35.0` | — | sudut torso minimum (°) untuk konfirmasi |
| `inspect_thr` | — | `0.40` | ambang gabungan kelas interaksi rak |
| `dwell_ratio` | `0.4` | `3.0` | toleransi gerak agar dianggap "diam" |
| `skip_dwell` | `false` | `true` | lewati cek diam (top-down tidak andal) |
| `confirm_windows` | `1` | `2` | jendela berturut sebelum alert keluar |
| `cooldown_seconds` | `30` | `90` | pembungkaman setelah alert |

Mengubah `jenis` lewat `PATCH` otomatis mengembalikan ambang-ambang di atas ke
default jenis baru, kecuali disebut eksplisit di permintaan yang sama.

---

## 5. Kalibrasi saat pemasangan

1. Pasang kamera, masukkan profilnya, jalankan.
2. Set `"preview": "video"` sementara, buka
   `http://localhost:8000/produksi/kamera/<id>/pratinjau` di browser.
3. Pastikan kerangka menempel benar pada orang dan tidak ada deteksi "hantu"
   di sudut frame. Kalau ada, naikkan `det_conf` atau `min_bbox_ratio`.
4. Peragakan kejadian (jatuh terkendali / berdiri lama di depan rak) dan pantau
   `GET /produksi/kejadian`.
5. Terlalu banyak false positive → naikkan `fall_thr` / `inspect_thr` atau
   `confirm_windows`. Terlalu banyak yang terlewat → turunkan.
6. **Kembalikan `"preview"` ke `"kerangka"` atau `"mati"` setelah selesai.**

Ukuran keberhasilan terbaik adalah rasio tanggapan staf: kalau sebagian besar
alert dari satu kamera ditandai `diabaikan`, ambang kamera itu terlalu longgar
untuk sudut pemasangannya.

---

## 6. Alert & anti-banjir notifikasi

Jendela geser menilai ulang tiap ~1 detik, jadi satu orang yang tergeletak akan
memenuhi syarat "jatuh" di setiap jendela berikutnya. Tanpa penanganan, staf
menerima puluhan notifikasi untuk satu peristiwa dan berhenti mempercayainya.

Dua lapis peredam:
- **Konfirmasi** — butuh `confirm_windows` jendela berturut. Meredam kedipan.
- **Cooldown** — setelah alert keluar, kombinasi (kamera, orang, jenis) yang sama
  dibungkam `cooldown_seconds`. Deteksi berulang hanya memperpanjang durasi
  kejadian yang sudah ada, tidak membuat alert baru.

Jatuh sengaja memakai `confirm_windows: 1` — untuk keadaan darurat, kecepatan
lebih berharga daripada kepastian ekstra satu detik.

### Human-in-the-loop

Setiap alert lahir berstatus `baru` dan **tidak memicu tindakan otomatis apa pun**.
Staf menanggapi lewat:

```bash
curl -X POST localhost:8000/produksi/kejadian/<id>/tanggapi \
     -H 'Content-Type: application/json' \
     -d '{"status": "dikonfirmasi", "oleh": "budi"}'
```

---

## 7. Privasi & kepatuhan

Ini bukan tempelan — melekat pada desain:

- **Pose-only.** Yang diproses hanya koordinat sendi. Sistem secara arsitektur
  tidak mengenali wajah atau identitas.
- **On-premise.** Semua inferensi terjadi di perangkat toko. Video mentah tidak
  perlu keluar dari lokasi.
- **Log metadata saja.** `kejadian.jsonl` memuat jenis kejadian, waktu, id kamera,
  skor, dan `track_id` sementara — **tanpa gambar, tanpa koordinat pose**.
  `track_id` hanya bermakna dalam satu sesi satu kamera; ia bukan identitas dan
  tidak bisa dipakai melacak orang antar kamera.
- **Retensi otomatis.** Kejadian melewati `SAPA_RETENSI_JAM` dihapus dari memori
  **dan** dari berkas.
- **Pratinjau privat secara default.** `preview: "kerangka"` mengirim kerangka di
  atas kanvas hitam; video mentah tidak pernah meninggalkan proses backend.
  Pratinjau juga hanya digambar selama ada yang menonton.
- **Jangan commit `data/cameras.json`** — memuat password kamera. Sudah masuk
  `.gitignore`.

Yang **masih harus disediakan tim** sebelum pemasangan nyata:
- Autentikasi & kontrol akses di depan `/produksi/*` (belum ada di kode ini).
- Papan pemberitahuan di lokasi: "area ini memakai analitik pose, bukan pengenalan wajah".
- Kajian kepatuhan UU PDP: dasar pemrosesan, hak subjek data, penanggung jawab.

---

## 8. Kebutuhan perangkat keras

Angka di bawah **indikatif dan wajib diukur ulang** di lokasi — throughput nyata
bergantung resolusi, jumlah orang per frame, dan `process_fps`.

- **Beban terbesar ada di YOLOv8-pose**, bukan di dua kepala BiLSTM. Kepala BiLSTM
  ~408k parameter dan ~0,12 ms per jendela — praktis gratis.
- **Edge per lokasi:** NVIDIA Jetson Orin — beberapa kamera per unit, video tidak
  keluar toko.
- **Atau server GPU on-prem:** satu GPU kelas menengah melayani beberapa aliran.
- Turunkan `process_fps` untuk menambah jumlah kamera per perangkat. Jendela 3
  detik tetap utuh karena buffer berbasis waktu, bukan jumlah frame — 6 fps sudah
  memadai untuk kamera rak.

**Anggaran latensi:** alert muncul beberapa detik setelah kejadian (jendela 3
detik + waktu inferensi).

---

## 9. Operasional

- `GET /produksi/kesehatan` — status tiap kamera: terhubung/tidak, fps
  terukur, umur frame terakhir, jumlah reconnect, error terakhir.
- **Reconnect otomatis** dengan backoff eksponensial (2 dtk → maks 30 dtk) saat
  kamera mati atau jaringan putus.
- **Auto-restart pekerja.** Pengawas memeriksa tiap 15 detik dan menyalakan ulang
  pekerja yang mati tak terduga — sistem toko tidak boleh butuh operator untuk
  hidup lagi.
- Dashboard menerima denyut kesehatan lewat `WS /ws/produksi/alert`, sehingga
  kamera mati terlihat tanpa menunggu alert yang tidak akan pernah datang.

### Ringkasan endpoint

| Metode | Jalur | Fungsi |
|---|---|---|
| `GET` | `/produksi/kamera` | daftar kamera + status |
| `POST` | `/produksi/kamera` | tambah kamera |
| `PATCH` | `/produksi/kamera/{id}` | ubah profil (pekerja restart otomatis) |
| `DELETE` | `/produksi/kamera/{id}` | hapus kamera |
| `POST` | `/produksi/kamera/{id}/mulai` | nyalakan |
| `POST` | `/produksi/kamera/{id}/berhenti` | matikan |
| `GET` | `/produksi/kamera/{id}/pratinjau` | aliran MJPEG |
| `GET` | `/produksi/kejadian` | log kejadian |
| `POST` | `/produksi/kejadian/{id}/tanggapi` | konfirmasi / abaikan |
| `GET` | `/produksi/kesehatan` | kesehatan sistem |
| `WS` | `/ws/produksi/alert` | alert langsung |

---

## 10. Uji

Logika produksi bisa diuji tanpa kamera, GPU, atau bobot model:

```bash
cd backend
python tests/uji_produksi.py    # buffer, debounce, profil, retensi  (butuh numpy)
python tests/uji_api.py         # wiring REST + WebSocket            (butuh fastapi)
```

`uji_api.py` men-stub cv2/torch/ultralytics, jadi keduanya jalan di mesin tanpa
dependensi berat.

---

## 11. Batasan yang diketahui

Jujur di depan — ini bahan "future work", bukan yang sudah selesai:

1. **Jurang domain deteksi jatuh.** Model dilatih di NTU RGB+D (jatuh diperagakan
   di lab). Peningkatan terpenting untuk akurasi produksi adalah mengumpulkan dan
   menganotasi data jatuh nyata dari sudut CCTV terpasang, lalu fine-tune.
2. **Belum ada autentikasi** pada endpoint produksi (bagian 7).
3. **Belum ada push mobile / webhook.** Alert saat ini keluar lewat WebSocket dan
   log; saluran FCM/webhook masih perlu dibangun.
4. **Kalibrasi masih manual** per kamera, belum ada zona rak berbasis poligon.
5. **Kondisi nyata** — cahaya redup, occlusion rak, kerumunan — membuat pose
   terputus. Sudah ada penanganan gap dan ambang confidence, tapi tetap perlu
   penyetelan per lokasi.
6. **Tracking bisa menukar ID** saat orang berpapasan. Cukup untuk memicu alert,
   dan SAPA memang tidak mengejar identitas — tapi berarti `track_id` tidak boleh
   diperlakukan sebagai orang yang pasti.
7. **Throughput belum diukur** pada perangkat target. Ukur sebelum menjanjikan
   jumlah kamera per unit.

---

*SAPA — Melihat Kebutuhan, Bukan Wajah.*
