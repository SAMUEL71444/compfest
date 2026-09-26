# Input SLICE OOF — opsional, belum tersedia

**Tidak ada hasil OOF dalam paket ini.** Pengguna mengonfirmasi bahwa yang tersedia hanya video GMGCSA24 dan video asli. Angka dalam `reports/` berasal dari inferensi end-to-end video, bukan cross-validation/OOF. Skrip berikut disiapkan untuk pemakaian selanjutnya, bukan untuk mengarang hasil yang hilang.

## Format aman untuk ekspor NPZ

Simpan NPZ tanpa object arrays/pickle. `dataset_npz` berisi metadata saja (jangan sertakan tensor pose X dalam file metadata ini):

- `sample_id`: string Unicode `[N]`, unik untuk setiap sampel/augmentasi.
- `y_true`: integer `[N]`, indeks kelas dalam urutan `class_names`.
- `group_id`: string `[N]`, ID klip asli sebelum augmentasi. Semua augmentasi dari satu klip harus masuk fold yang sama.
- `yaw_deg`, `pitch_deg`: angka `[N]` opsional; `NaN` untuk metadata yang tidak diketahui. Pakai sudut yang benar dari proses augmentasi, bukan arah jatuh dari nama video.
- `performer`: string `[N]` opsional; ID anotasi subjek, string kosong bila tidak diketahui.

`oof_npz` berisi:

- `sample_id`: string `[N]`, cakupan tepat sama dengan dataset; urutan boleh berbeda karena join memakai ID.
- `fold`: integer `[N]`, minimal dua fold held-out.
- `y_pred`: integer `[N]`, atau `y_prob`: float `[N,C]`, probabilitas finite dan jumlah tiap baris 1.
- Jika keduanya disediakan, `y_pred` harus sama dengan argmax `y_prob`.

Pembuat data bertanggung jawab memastikan setiap prediksi dihasilkan model yang **tidak dilatih pada sampel/grup tersebut**. Skrip memeriksa duplikasi ID, cakupan, probabilitas, dan konsistensi grup/fold, tetapi tidak dapat membuktikan isi training dari NPZ saja. Untuk klaim generalisasi antar-subjek, gunakan split berdasarkan performer dan catat protokolnya.

## Menjalankan

Isi salinan `fall_oof.template.json` atau `interaction_oof.template.json` dengan lokasi input dan provenance training nyata, lalu dari root repository:

```bash
backend/.venv/bin/python "eval/infrence fall/scripts/evaluate_oof.py" \
  --config "eval/infrence fall/inputs/fall_oof.json" \
  --output "eval/infrence fall/oof/fall-run-01"
```

Folder output harus baru agar hasil sebelumnya tidak tertimpa. Evaluasi fall menghasilkan recall per yaw, pitch, kombinasi yaw/pitch, dan performer jika metadatanya ada. Tidak ada asumsi bahwa jumlah sudut pasti 15; grup berasal dari metadata nyata.

Evaluasi interaksi menghasilkan confusion matrix, F1 tiap kelas, serta `class_pairs.csv`. Untuk setiap pasangan A/B, subset adalah **label aktual A atau B**; prediksi ke kelas lain tetap dihitung sebagai kesalahan, tidak dibuang. `pair_macro_f1_zero_division_0` adalah rata-rata F1 A/B pada subset itu (undefined F1 dihitung 0); sertakan support masing-masing dan jumlah prediksi keluar pasangan. Ini adalah definisi analisis pasangan, bukan macro-F1 seluruh dataset.

Metrik OOF adalah **per sampel/jendela dengan keputusan argmax**, sedangkan baseline video memakai probabilitas jatuh >=0.8 dan konfirmasi geometri. Jangan membandingkannya sebagai metrik yang setara.
