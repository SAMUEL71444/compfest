# Verifikasi

Paket laporan diverifikasi terhadap hash kode, model, manifest, dan video pada saat laporan dibuat. Lihat `verification.json` untuk ringkasannya.

Hasil pemeriksaan:

- `reporting_tests.log`: 8/8 tes metrik, alignment OOF, validasi probabilitas, dan pencegahan leakage lulus.
- `pipeline_tests.log`: 6/6 tes evaluator dan penanganan waktu/frame lulus.
- `architecture_check.log`: 8/8 pemeriksaan kesesuaian kepala jatuh dan interaksi dengan arsitektur training lulus.

Folder `source/` adalah runtime checkpoint terisolasi yang hash-nya dicatat pada run. Salinan itu menjaga reproduksibilitas tanpa mengubah kode produksi di `backend/`.
