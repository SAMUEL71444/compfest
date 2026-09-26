# SAPA — baseline inference jatuh

Paket ini mengevaluasi dua sumber secara terpisah dengan bobot dan aturan inferensi yang sama:

- **GMGCSA24:** 5 dari 6 video terdeteksi; recall 83,33%; F1 jatuh 90,91%.
- **Video asli:** 2 dari 4 video terdeteksi; recall 50,00%; F1 jatuh 66,67%.

Semua klip diberi label positif jatuh berdasarkan keterangan pengguna. Karena tidak ada video negatif, specificity, false-positive rate, balanced accuracy, dan ROC-AUC tidak dapat dihitung. Precision bernilai 100%, tetapi angka itu belum menguji alarm palsu. Accuracy pada kumpulan positif sama dengan recall dan tidak boleh dipakai sebagai gambaran performa umum.

Dataset GMGCSA24 saat ini telah dipilih ulang setelah evaluasi sebelumnya. Perbedaan skor terhadap run lama menggambarkan perubahan komposisi data, bukan peningkatan model.

Artefak sebelum pemindahan struktur dipertahankan di `archive/pre-structure/`. Hasil aktif memakai run terbaru yang tercantum di `reproducibility/verification.json`.

![Recall per sumber](figures/recall_by_dataset.png)

## Navigasi

- [Laporan interaktif lokal](index.html)
- [Laporan GMGCSA24](reports/gmgcsa24/README.md)
- [Laporan video asli](reports/vidio_asli/README.md)
- [Analisis per-irisan data](reports/SLICE.md)
- [Status irisan yang diminta](reports/requested_slices_status.json)
- [Inventaris video dan metadata](metadata/video_inventory.csv)
- [Bukti reproducibility](reproducibility/verification.json)
- [Log dan ringkasan validasi](reproducibility/README.md)
- [Format data OOF/NPZ untuk evaluasi lanjutan](inputs/README.md)

## Konfigurasi yang dikunci

Inference memakai target 15 FPS, window 45, stride 15, ambang probabilitas jatuh 0,80, konfirmasi sudut torso 35 derajat, dan kepala interaksi dinonaktifkan. Manifest, hash model, hash pipeline, hash video, environment, hasil per klip, serta log tersimpan di `runs/`.

## Analisis SLICE

Data yang tersedia mendukung irisan berdasarkan sumber dataset, resolusi, FPS, dan durasi. Hasilnya bersifat deskriptif karena hanya ada 10 video dan seluruhnya positif.

Yaw/pitch kamera, performer, dan pasangan kelas interaksi belum dapat dihitung karena metadata dan prediksi OOF belum tersedia. Nilai tersebut tidak diperkirakan dari nama file, wajah, pakaian, atau arah jatuh. `scripts/evaluate_oof.py` dan template di `inputs/` siap digunakan ketika data valid tersedia.

## Reproduksi

Jalankan dari root repository:

```bash
backend/.venv/bin/python "eval/infrence fall/scripts/run_all.py"
```

Untuk membuat ulang laporan dari run yang sudah ada tanpa inference:

```bash
backend/.venv/bin/python "eval/infrence fall/scripts/run_all.py" --reports-only
```

Tes pelaporan:

```bash
backend/.venv/bin/python -m unittest discover -s "eval/infrence fall/tests" -v
```

Cuplikan PNG di `reports/*/frames/` berasal dari video sumber dan disertai indeks frame serta timestamp. Cuplikan itu adalah bukti input dan keputusan per klip, bukan anotasi ground-truth waktu kejadian dan bukan bukti bahwa seluruh rentang prediksi tepat.
