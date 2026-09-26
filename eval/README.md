# Evaluasi SAPA — peta dokumentasi

Ada tiga sumber evaluasi terpisah di `eval/`, mengukur hal yang berbeda.
Bagian ini menautkan ketiganya dan menjelaskan rumus yang dipakai. Sisa
dokumen di bawah (mulai "Test Suite SAPA") adalah manual teknis untuk
sumber ketiga (`./eval/uji`) — tidak berubah.

## 1. Confusion matrix OOF — data NTU/MERL (cross-validation)

5-fold out-of-fold pada dataset training (NTU untuk jatuh, MERL untuk
interaksi). Mengukur kualitas kedua kepala BiLSTM secara terisolasi dari
YOLOv8-pose/tracking, di kondisi data yang sudah bersih.

- **Hasil:** [eval/hasil/README.md](hasil/README.md) — confusion matrix,
  F1 per kelas, F1 per pasangan kelas, dengan grafik dan CSV.
- **Data mentah:** `eval/fall_cv_summary.json`, `eval/interaction_cv_summary.json`
- **Skrip:** `eval/analisis_baseline.py` (jalankan ulang dengan
  `backend/.venv/bin/python eval/analisis_baseline.py`)
- **Ringkasan:** Kepala Jatuh akurasi 0.897 / macro-F1 0.871 (3 kelas:
  normal/oleng/jatuh). Kepala Interaksi macro-F1 0.548 mentah (6 kelas),
  naik ke macro-F1 0.762 setelah digabung jadi 2 kelas
  (`inspecting` = inspect_product+inspect_shelf vs `other`) — metrik 2 kelas
  ini yang relevan karena pipeline produksi (`pipeline/analyze.py`) memang
  hanya mengecek argmax masuk `inspect_idx`, bukan 6 kelas penuh.

## 2. Baseline jatuh di video nyata — GMGCSA24 & video asli

Inference end-to-end (YOLOv8-pose + tracking + kepala jatuh) pada video
CCTV/HP sungguhan, bukan data training. Semua klip berlabel positif jatuh,
jadi hanya recall/F1 yang valid — tidak ada video negatif untuk mengukur
alarm palsu di sini (lihat sumber #3 untuk itu).

- **Hasil:** [eval/infrence fall/README.md](infrence%20fall/README.md)
- **Ringkasan:** GMGCSA24 5/6 video (recall 83,33%, F1 90,91%); video asli
  2/4 video (recall 50,00%, F1 66,67%).
- **Analisis irisan (SLICE):** [eval/infrence fall/reports/SLICE.md](infrence%20fall/reports/SLICE.md)
  — per dataset/resolusi/FPS/durasi. Irisan yaw/pitch kamera dan performer
  **belum bisa dihitung** (metadata sudut & ID subjek tidak tersedia).

## 3. Test suite berlabel — `./eval/uji` (recall/precision/F1 level kejadian)

Pipeline penuh dijalankan atas klip di `eval/video/` dan dicocokkan ke
label kejadian di `eval/label.csv` lewat tumpang-tindih waktu. Ini satu-
satunya sumber yang mengukur **alarm palsu** (lewat klip berlabel `kosong`)
dan **fitur yang belum ada** (lewat klip berlabel tapi sistem tidak punya
mekanismenya).

- **Manual lengkap:** sisa dokumen ini di bawah.
- **Hasil terbaru:** [eval/hasil/category5_field_test.md](hasil/category5_field_test.md)
  — uji lapangan video toko nyata (Jason & Mama), termasuk temuan bahwa
  fitur angkat tangan **belum diimplementasikan** di baseline (recall 0.000
  pada klip `angkat_tangan`, run `20260925-0955`/`2227`/`2230`).
- **Arsip run jatuh** (`Tes1.mp4`, run `20260925-0704`/`0707`/`0711`):
  recall 1.000/precision 1.000 di ambang lama maupun baru — lihat "Catatan
  dari klip yang sudah diuji" di bawah untuk kenapa angka ini tidak
  membuktikan ambang mana yang lebih baik.
- **Bandingkan run:** `python3 eval/banding.py`

## Rumus metrik yang dipakai (ketiganya)

Semua confusion matrix `cm[i, j]` = jumlah sampel kelas asli `i` yang
diprediksi sebagai kelas `j`. Untuk kelas `i`:

```
TP(i) = cm[i, i]
FN(i) = sum(cm[i, :]) - TP(i)        # kelas i, salah diprediksi jadi kelas lain
FP(i) = sum(cm[:, i]) - TP(i)        # kelas lain, salah diprediksi jadi i

recall(i)    = TP(i) / (TP(i) + FN(i))     = TP(i) / dukungan_aktual(i)
precision(i) = TP(i) / (TP(i) + FP(i))     = TP(i) / jumlah_diprediksi(i)
F1(i)        = 2 * precision(i) * recall(i) / (precision(i) + recall(i))

akurasi   = sum(TP semua kelas) / total sampel
macro-F1  = rata-rata tidak berbobot F1(i) di semua kelas
```

**F1 per pasangan kelas** (dipakai di sumber #1 untuk cari pasangan
paling tertukar, mis. reach × retract): dihitung dari baris aktual dua
kelas terkait saja, tapi prediksi yang jatuh ke kelas ketiga (di luar
pasangan) tetap dihitung sebagai kesalahan — bukan dibuang. Ini membuat
angkanya konsisten dengan F1 per kelas di atas.

**Untuk sumber #3** (test suite level-kejadian), "kejadian" dianggap
tertangkap (TP) bila rentang waktu deteksi tumpang-tindih (dengan
toleransi ±1,5 detik) dengan rentang waktu di label — bukan kecocokan
detik-persis. Lihat "Metrik: kenapa yang ini" di bawah untuk alasannya.

## Kenapa tiga sumber, bukan satu

Rulebook Eval Track minta analisis "irisan ketahanan" dan "titik mana
sistem gagal" — satu angka gabungan menyembunyikan itu. Sumber #1 mengukur
kepala model saja (bersih dari noise pose estimation). Sumber #2 mengukur
pipeline penuh tapi hanya kasus positif jatuh. Sumber #3 mengukur pipeline
penuh dengan kasus negatif (alarm palsu) dan kejadian yang fiturnya belum
ada sama sekali. Ketiganya saling melengkapi, bukan duplikat.

---

# Test Suite SAPA

Jalankan pipeline SAPA pada klip video berlabel, lalu ukur berapa kejadian
yang tertangkap dan berapa yang terlewat.

## Cara pakai — 3 langkah

### 1. Taruh video

```
eval/video/klip_kamu.mp4
```

Format: `.mp4`, `.mov`, `.avi`, `.mkv`. Boleh berapa pun banyaknya.

### 2. Tulis label di `eval/label.csv`

Satu baris = satu kejadian yang **seharusnya** terdeteksi:

```csv
video,tipe,mulai,akhir,catatan
klip_kamu.mp4,jatuh,7.5,11.0,jatuh pelan di lorong
klip_kamu.mp4,angkat_tangan,25.0,29.0,pelanggan panggil pegawai
klip_lain.mp4,kosong,0,0,tidak ada kejadian - ukur alarm palsu
```

| kolom | isi |
|---|---|
| `video` | nama file persis seperti di `eval/video/` |
| `tipe` | `jatuh` · `angkat_tangan` · `butuh_bantuan` · `kosong` |
| `mulai`, `akhir` | detik (boleh desimal) |
| `catatan` | bebas — muncul saat kejadian terlewat |

**`kosong`** untuk klip yang tidak ada kejadian sama sekali. Apa pun yang
terdeteksi di situ dihitung alarm palsu. Klip semacam ini penting: tanpanya,
sistem yang menandai segalanya akan terlihat sempurna.

Tanpa label pun suite tetap jalan — deteksi hanya dicatat, tidak dinilai.

### 3. Jalankan

```bash
./eval/uji
```

Butuh container jalan dulu (`docker compose up -d`). Semua dependensi ada di
situ, jadi tidak perlu memasang torch di laptop.

## Pilihan lain

```bash
./eval/uji --klip Tes1.mp4          # satu klip saja
./eval/uji --preset prob_saja       # preset ambang lain
./eval/uji --fall-thr 0.80 --fall-angle 35   # coba ambang lama
./eval/uji --verbose                # tampilkan semua deteksi
```

Preset: `prob_sudut` (default) · `prob_saja` · `prob_kecepatan` · `prob_sudut_kecepatan`

## Membaca hasilnya

```
  Tes1.mp4 ... 147 detik, 8 deteksi
      jatuh          tp=4 fn=0 fp=0  OK

  RINGKASAN
  jatuh           recall 1.000   precision 1.000   f1 1.000
```

- **tp** tertangkap benar · **fn** terlewat · **fp** alarm palsu
- **recall** — dari sekian kejadian, berapa yang tertangkap
- **precision** — dari sekian deteksi, berapa yang benar

Kejadian yang terlewat dicetak beserta catatannya:

```
         TERLEWAT  33.0-37.0s  — jatuh pelan, orang jauh
```

Itulah keluaran paling berguna: bukan angkanya, melainkan **kasus mana** yang
gagal. Dari situ arah perbaikan jadi jelas.

## Berkas hasil

Tiap run menyimpan **dua** berkas ke `eval/hasil/`:

```
20260925-0704_prob_sudut_thr0.65_ang5_spd0.00.json
20260925-0704_prob_sudut_thr0.65_ang5_spd0.00.md
```

Namanya memuat tanggal-jam dan ambang yang dipakai, jadi dua run dengan preset
sama tapi ambang berbeda tetap bisa dibedakan tanpa membuka isinya.

- **`.json`** — lengkap, termasuk tiap deteksi. Untuk diolah lebih lanjut.
- **`.md`** — laporan siap baca: tabel ringkasan, daftar kegagalan, waktu
  proses per klip. Bisa langsung disalin ke Evaluation Artifact.

Isi laporan `.md`:

```markdown
## Ringkasan
| Kejadian | Recall | Precision | F1 | Tertangkap | Terlewat | Alarm palsu |
|---|---|---|---|---|---|---|
| jatuh | 1.000 | 1.000 | 1.000 | 4 | 0 | 0 |

## Kegagalan
| Klip | Jenis | Masalah | Waktu | Catatan |
|---|---|---|---|---|
| klip2.mp4 | jatuh | TERLEWAT | 33.0-37.0s | jatuh pelan, orang jauh |
```

## Membandingkan beberapa run

```bash
python3 eval/banding.py
```

Menampilkan semua run berdampingan beserta selisih recall terhadap run
pertama — untuk menjawab "apakah perubahan ini memperbaiki atau memperburuk"
tanpa membandingkan berkas JSON satu per satu.

```
  ambang                            jatuh                bantuan
                             recall  prec    f1     recall  prec    f1
  prob_sudut 0.65/5.0/0.0    1.000  1.000  1.000         -
  prob_sudut 0.8/35.0/0.0    1.000  1.000  1.000         -

  Selisih recall jatuh terhadap run pertama:
    0.8/35.0  +0.000  (sama)
```

## Metrik: kenapa yang ini

**recall** metrik utama untuk jatuh. Kejatuhan yang terlewat berarti orang
tergeletak tanpa pertolongan; satu alarm palsu tinggal diabaikan operator.
Biaya kedua kesalahan itu tidak setara.

**precision** tetap diukur karena alarm palsu yang terlalu sering membuat
operator berhenti percaya — recall tinggi jadi tidak berarti.

**Kecocokan memakai tumpang-tindih waktu**, bukan titik persis. Satu kejatuhan
berlangsung beberapa detik dan jendela model bergeser 1 detik, jadi menuntut
kecocokan detik-per-detik menghukum sistem untuk hal yang tidak penting
secara operasional.

## Yang TIDAK tertangkap suite ini

- **Lapisan mana yang gagal.** Kalau recall rendah, suite tidak memberi tahu
  apakah YOLOv8-pose yang meleset atau kepala BiLSTM yang salah menilai.
  Perlu diperiksa manual lewat `--verbose`.
- **Hanya seakurat labelnya.** Label yang salah menghasilkan angka yang salah.
- **Seragam pegawai belum dinilai otomatis.** Perlu klip berisi pegawai
  berseragam terdaftar; cakupannya (pegawai dikecualikan dari butuh-bantuan
  tapi tetap dicek jatuh) sejauh ini baru diverifikasi manual.

## Catatan dari klip yang sudah diuji

`Tes1.mp4` memberi recall 1.000 / precision 1.000 — **dan hasil yang sama
persis** dengan ambang lama (0,80/35°) maupun baru (0,65/5°).

Itu bukan berarti kedua ambang setara. Artinya klip ini **tidak bisa
membedakan keduanya**: keempat kejatuhannya terlalu jelas (probabilitas
≥0,91, sudut torso ≥52°), tidak ada satu pun kasus batas.

Klip yang paling berguna justru yang sulit:
- jatuh pelan / merosot perlahan, bukan roboh
- jatuh tidak sempurna — terduduk, tersangkut rak
- orang jauh dari kamera
- klip **tanpa kejadian** untuk mengukur alarm palsu
- stretching, tos, melambai — untuk menguji false positive angkat tangan
