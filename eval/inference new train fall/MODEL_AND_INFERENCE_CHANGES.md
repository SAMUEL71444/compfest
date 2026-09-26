# Perubahan model AI dan logika inferensi

## Perubahan model AI

Bobot kepala jatuh berubah dari model lama ke model baru:

- model lama `backend/models/fall_head.pt`: SHA-256 `411eebcbfbcaa59cde5941462d7e5190571168553f392c2d4a665f0b9169eebe`;
- model baru `models/fall_head.pt`: SHA-256 `770735e5b9eb722da403fb91d358f14591b291e32c26fb4efa6d547ff776c733`.

Arsitektur tidak berubah: input 24, BiLSTM dua arah dengan hidden size 128 dan dua layer, dropout 0,3, mean pooling, LayerNorm, lalu Linear untuk kelas `normal`, `oleng`, dan `jatuh`. Model baru dilatih 25 epoch pada seluruh data setelah validasi silang lima fold. Artefak training melaporkan macro-F1 fold `87,56% ± 2,18%` dan recall jatuh `85,41% ± 1,06%`.

Kode training baru menghitung fitur geometri pada pose ternormalisasi, melakukan threshold sweep atas probabilitas, sudut, dan kecepatan, lalu menyimpan enam kandidat di `threshold_best_models.json`. Paket ini tidak menyatakan perubahan proses training model lama karena source training lama tidak tersedia untuk dibandingkan.

## Perubahan logika inferensi jatuh

Logika lama yang tersimpan pada paket baseline menggunakan:

```text
probabilitas_jatuh >= fall_thr
AND sudut_torso_raw >= fall_angle
```

Logika baru mengikuti `new_train_now.py` dan `fall_head.json`:

```text
probabilitas_jatuh >= T_prob
AND sudut_maks_torso_normalized >= T_angle
AND kecepatan_maks_perubahan_vektor_torso >= T_speed
```

Sudut baru dihitung sebagai nilai maksimum sudut vektor pinggul-ke-bahu terhadap vertikal sepanjang window. Kecepatan dihitung sebagai maksimum norma perubahan vektor torso antar-frame dikali 15 FPS. Keduanya memakai pose ternormalisasi yang sama dengan input model.

Konfigurasi utama tidak dibuat manual. `scripts/run_all.py` membaca kandidat yang dirujuk oleh `threshold_recommended` dalam `fall_head.json`, lalu memverifikasi nilainya terhadap `threshold_best_models.json`:

```text
kandidat = F1_terbaik
T_prob   = 0.65
T_angle  = 5.0
T_speed  = 0.0
```

Karena `T_speed=0`, komponen kecepatan tersedia dalam implementasi tetapi tidak menyaring window pada konfigurasi utama ini.

## Dampak terukur

Dengan konfigurasi rekomendasi utama dan kumpulan video yang sama:

- GMGCSA24 tetap `5/6`: recall `83,33%`, F1 `90,91%`;
- video asli berubah dari `2/4` menjadi `3/4`: recall `50,00% → 75,00%`, F1 `66,67% → 85,71%`.

Kandidat `recall_tertinggi_FARwajar` menghasilkan `6/6` dan `4/4`, tetapi hanya disimpan sebagai analisis alternatif karena bukan `threshold_recommended`. Pada OOF training kandidat tersebut juga memiliki false-alarm rate lebih tinggi: `3,09%`, dibanding `2,10%` pada `F1_terbaik`.

Semua sepuluh video adalah contoh positif jatuh. Evaluasi video ini mengukur recall, tetapi tidak menyediakan video negatif untuk mengukur specificity atau false-positive rate end-to-end.

## Bukti

- `source/new_train_now.py`: kode training yang diberikan;
- `models/fall_head.pt` dan `models/fall_head.json`: bobot dan konfigurasi model baru;
- `training_artifacts/fall_cv_summary.json`: hasil validasi silang;
- `training_artifacts/threshold_best_models.json`: kandidat keputusan dari training;
- `reports/comparison_old_vs_new.csv`: perbandingan video lama dan baru;
- `reports/comparison_threshold_profiles.csv`: perbandingan dua profil threshold;
- `runs/`: evidence, hash, konfigurasi, dan log setiap eksekusi.
