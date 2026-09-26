# Uji Lapangan Baseline — Video Toko Nyata

## Konteks
Video diambil dari toko nyata (warung + minimarket) menggunakan kode MVP
hasil Babak Penyisihan (SEBELUM perubahan apa pun di Fase Iteration).
Tujuan: identifikasi kelemahan baseline sebelum perbaikan.

## Temuan 1 — Fitur sinyal aktif (angkat tangan) belum ada di baseline
MVP penyisihan hanya memiliki sinyal pasif (dwell time + inspeksi berulang
dari kepala interaksi). Tidak ada mekanisme deteksi gestur aktif seperti
angkat tangan.

| Kasus | Ekspektasi | Hasil | Status |
|---|---|---|---|
| Jason angkat tangan | butuh bantuan | tidak terdeteksi | GAGAL (fitur belum ada) |
| Mama angkat tangan | butuh bantuan | tidak terdeteksi | GAGAL (fitur belum ada) |

**Tally:** 0/2 terdeteksi. **Penyebab tervalidasi:** bukan bug — fitur ini
memang belum diimplementasikan saat submisi penyisihan.

Konsisten dengan hasil test suite otomatis (`./eval/uji`) yang tersimpan di
`eval/hasil/20260925-0955..md`, `20260925-2227..md`, dan `20260925-2230..md`:
klip `Salinan Mama (angkat tangan).mp4` diberi label `angkat_tangan` di
`eval/label.csv`, dan pada tiga run tersebut recall = 0.000 (0 dari 1
tertangkap) — sistem tidak memiliki mekanisme untuk kelas kejadian ini sama
sekali, bukan kegagalan model pada kasus sulit.

## Temuan 2 — Kualitas pose estimation pada kondisi CCTV nyata
- **Tinggi subjek:** subjek bertubuh lebih pendek menunjukkan skeleton
  kurang stabil dibanding subjek tinggi.
- **Latensi:** pada beberapa klip, overlay skeleton tampak mendahului/
  tertinggal dari gerakan aktual subjek (indikasi lag pipeline).
- **Kepadatan multi-orang:** saat 2+ orang berdekatan dalam satu frame,
  kualitas skeleton kedua individu menurun.

## Yang BERFUNGSI dengan baik di baseline
- Tracking multi-orang stabil, ID konsisten (diuji hingga 5+ orang di mode live).
- Deteksi sinyal pasif (dwell/inspeksi) berhasil membedakan status dua
  orang berbeda secara independen dalam satu frame.
- Deteksi jatuh pada klip uji terkontrol (`Tes1.mp4`, arsip run
  `20260925-0704`/`0707`/`0711`) mencapai recall 1.000 / precision 1.000 di
  ambang lama (0,80/35°) maupun baru (0,65/5°) — lihat catatan di
  `eval/README.md` soal keterbatasan klip ini (kejatuhannya terlalu jelas,
  tidak ada kasus batas).

## Rencana Iterasi (checkpoint 2)
- [ ] Implementasi deteksi angkat tangan (aturan: wrist > shoulder,
      bertahan >=2-3 detik, bukan sedang reach/hand-in-shelf)
- [ ] Uji ulang video yang SAMA (Jason & Mama angkat tangan) setelah
      fitur diimplementasikan -> bandingkan before/after
- [ ] Investigasi lag pipeline pose estimation (kemungkinan bottleneck
      di FPS processing vs FPS video)
