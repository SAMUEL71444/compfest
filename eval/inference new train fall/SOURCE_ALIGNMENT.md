# Audit kesesuaian dengan kode dan artefak yang diberikan

Dokumen ini memisahkan bagian yang dapat dibuktikan langsung dari file sumber dan bagian yang masih bergantung pada pipeline video yang tersedia.

## Terbukti langsung

- `source/new_train_now.py`, `models/fall_head.pt`, `models/fall_head.json`, `training_artifacts/fall_cv_summary.json`, dan `training_artifacts/threshold_best_models.json` adalah salinan byte-identik dari file yang diberikan. Hash artefak dicatat di setiap `evidence.json`; `source_snapshot.json` mencatat hash pipeline inferensi.
- Arsitektur inferensi mengikuti `FallLSTM` pada kode training: BiLSTM dua arah, hidden size 128, dua layer, dropout 0,3, mean pooling sepanjang waktu, LayerNorm, Dropout, lalu Linear tiga kelas.
- Input model mengikuti konfigurasi: 12 sendi COCO indeks 5 sampai 16, kanal x dan y, sehingga dimensi input 24; window 45 frame; stride 15; target 15 FPS.
- Fitur geometri mengikuti fungsi `geom_features`: sudut maksimum vektor pinggul-ke-bahu terhadap vertikal dan kecepatan maksimum perubahan vektor torso dikali 15 FPS.
- Profil aktif mengikuti `threshold_recommended` dari konfigurasi model: `F1_terbaik` (`T_prob=0,65`, `T_angle=5`, `T_speed=0`). Hasil kandidat resmi lain, `recall_tertinggi_FARwajar` (`0,30`, `0`, `0`), disimpan sebagai pembanding dan bukan konfigurasi utama.

## Batas kesesuaian

Kode training menerima array NPZ yang sudah dinormalisasi dan tidak memuat implementasi ekstraksi video, tracking, pengisian keypoint hilang, atau fungsi `normalize_pose`. Untuk video mentah, paket ini memakai salinan pipeline video proyek yang tersedia. Konfigurasi model memang menyebut urutan `YOLOv8 -> normalize_pose -> resample_fps(15)`, tetapi kesamaan numerik preprocessing dengan pembuat NPZ training tidak dapat dibuktikan tanpa kode pembentukan NPZ tersebut.

Profil recall pernah dicoba setelah profil rekomendasi F1 melewatkan dua dari sepuluh video positif. Karena itu, hasil 10/10 pada profil pembanding tersebut adalah hasil pada suite yang sudah dilihat, bukan evaluasi holdout. Semua video juga positif jatuh, sehingga precision video tidak menguji false positive. Acuan risiko false positive yang tersedia adalah OOF training pada artefak: 3,09% untuk profil recall dan 2,10% untuk profil F1.
