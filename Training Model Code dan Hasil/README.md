# Kode Training & Hasil Eksperimen

Notebook pelatihan kedua kepala model SAPA beserta arsitektur pembanding yang
diuji sebelum arsitektur final dipilih. Semua dijalankan di Google Colab.

Folder ini **tidak dijalankan oleh aplikasi web** — ia adalah dokumentasi
bagaimana bobot di `backend/models/` dihasilkan.

## Kepala Jatuh — `Train_fall/`

Dataset: NTU RGB+D (aksi jatuh dan aksi normal sebagai pembanding).
Masukan: 12 sendi badan (indeks 5–16) × koordinat (x, y) = 24 dimensi.

| Notebook | Arsitektur | Peran |
|---|---|---|
| `Train_fall(BiLSTM).ipynb` | **BiLSTM** | ✅ **dipakai produksi** → `fall_head.pt` |
| `STGCN.ipynb` | ST-GCN | pembanding, graf spasial-temporal |
| `TCN.ipynb` | Temporal CNN | pembanding |
| `Baseline.ipynb` | MLP, CNN1D | garis dasar sederhana |

## Kepala Interaksi — `Interaction/`

Dataset: MERL Shopping Dataset (aktivitas pelanggan di rak).
Masukan: 17 sendi × (x, y, confidence) = 51 dimensi.

| Notebook | Arsitektur | Peran |
|---|---|---|
| `Kepala Interaksi(BiLSTM).ipynb` | **BiLSTM** | ✅ **dipakai produksi** → `interaction_head.pt` |
| `Baseline.ipynb` | MLP, CNN1D, TCN | pembanding |

## Invarian yang menghubungkan training dengan aplikasi

Ketiga hal berikut **wajib sama persis** antara notebook di sini dan
`backend/pipeline/`. Bila berbeda, model tetap termuat tanpa error tetapi
prediksinya menjadi tidak bermakna — kegagalan senyap yang sulit dilacak.

1. **Agregasi temporal** — `out.mean(dim=1)` (mean-pooling seluruh langkah
   waktu), bukan hidden state terakhir.
2. **Normalisasi pose** — origin di titik tengah pinggul, skala panjang torso,
   dihitung per frame.
3. **Bentuk jendela** — 45 frame @ 15 fps (3 detik), stride 15.

Kesesuaiannya dikunci oleh `backend/tests/uji_arsitektur.py`, yang menyalin
arsitektur dari notebook di folder ini lalu membandingkan keluarannya terhadap
`pipeline/models.py`:

```bash
cd backend && .venv/bin/python tests/uji_arsitektur.py
```

## Hasil

`Hasil.docx` memuat ringkasan metrik hasil eksperimen antar arsitektur.
