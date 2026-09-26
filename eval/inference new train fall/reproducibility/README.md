# Verifikasi inference model fall baru

- `tests.log`: 20/20 tes lulus, termasuk kecocokan arsitektur bobot, threshold artefak, rumus geometri training, metrik, dan timing.
- `verification.json`: hash pipeline, model, konfigurasi, artefak training, manifest, dan seluruh video cocok saat laporan dibuat.
- `source/backend/`: snapshot pipeline terisolasi; `backend/` produksi tidak diubah.
- `../source/new_train_now.py`: salinan byte-for-byte kode training yang diberikan pengguna.

Inference default memakai `threshold_recommended` dari `fall_head.json`, yaitu kandidat `F1_terbaik`. Kandidat `recall_tertinggi_FARwajar` yang pernah dicoba tetap disimpan terpisah sebagai perbandingan dan tidak menjadi konfigurasi utama.

Arsitektur model dan geometri dapat dicocokkan langsung dengan kode training. Tahap video-ke-pose memakai pipeline proyek yang tersedia karena kode pembentukan NPZ training tidak disertakan; lihat `../SOURCE_ALIGNMENT.md`.
