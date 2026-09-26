/* ─────────────────────────────────────────────────────────────────────────────
   dedupeEvents — gabungkan event kejadian yang sebenarnya "satu peristiwa"
   tapi dipecah backend menjadi banyak potongan per-window.

   Backend mengirim event "jatuh" PER-WINDOW → sering duplikat berurutan untuk
   track_id yang sama. Begitu juga "butuh_bantuan" di mode Live (spam per ~1 dtk).
   Util ini menyatukan event dengan (track_id + tipe) sama yang OVERLAP atau
   BERDEKATAN menjadi SATU event dengan rentang waktu penuh.

   Dipakai di /analisis (ResultPage) DAN /live (LivePage) — SATU sumber logika.
───────────────────────────────────────────────────────────────────────────── */

// Jarak antar-event (detik) yang masih dianggap satu peristiwa berkelanjutan.
const GAP_JATUH = 1.5   // jatuh: window rapat, gap kecil
const GAP_BANTU = 4.0   // butuh bantuan: aktivitas bisa terputus sesaat

/**
 * ID stabil untuk sebuah event — dipakai sebagai key React & kunci status
 * (ditangani / alarm palsu) di mode Live. Berbasis awal peristiwa sehingga
 * tetap sama walau kartu diperbarui saat peristiwa masih berlangsung.
 */
export function eventId(ev) {
  return `${ev.track_id}__${ev.tipe}__${Math.round((ev.t0 ?? 0) * 100) / 100}`
}

function gapUntuk(tipe) {
  return tipe === 'jatuh' ? GAP_JATUH : GAP_BANTU
}

/**
 * Gabungkan event yang overlap / berdekatan.
 *
 * @param {Array} events - array event mentah dari backend
 * @returns {Array} event tergabung, terurut menaik berdasarkan t0
 *
 * Hasil gabungan tiap event:
 *   t0     = paling awal
 *   t1     = paling akhir
 *   durasi = t1 - t0 (detik)
 *   skor   = maksimum dari anggota
 *   sinyal = "aktif" bila salah satu anggota aktif (khusus butuh_bantuan)
 *   _count = jumlah event mentah yang tergabung (opsional, untuk debug/badge)
 */
export function dedupeEvents(events) {
  if (!Array.isArray(events) || events.length === 0) return []

  // Urutkan menaik by t0 supaya penggabungan berurutan valid.
  const sorted = [...events].sort((a, b) => (a.t0 ?? 0) - (b.t0 ?? 0))

  // Simpan satu "event aktif" per kunci (track_id + tipe) untuk digabung.
  const aktif = new Map()   // key → merged event
  const hasil = []

  for (const ev of sorted) {
    const key = `${ev.track_id}__${ev.tipe}`
    const t0 = ev.t0 ?? 0
    const t1 = ev.t1 ?? t0
    const prev = aktif.get(key)

    const bisaGabung =
      prev && t0 <= (prev.t1 + gapUntuk(ev.tipe))   // overlap atau gap dalam ambang

    if (bisaGabung) {
      prev.t1     = Math.max(prev.t1, t1)
      prev.t0     = Math.min(prev.t0, t0)
      prev.durasi = +(prev.t1 - prev.t0).toFixed(2)
      prev._count += 1
      if (ev.skor != null) {
        prev.skor = prev.skor == null ? ev.skor : Math.max(prev.skor, ev.skor)
      }
      // Field opsional: pertahankan nilai "terkuat" bila ada.
      if (ev.sinyal === 'aktif') prev.sinyal = 'aktif'
      if (ev.sudut_torso != null) {
        prev.sudut_torso = Math.max(prev.sudut_torso ?? 0, ev.sudut_torso)
      }
    } else {
      const merged = {
        ...ev,
        t0,
        t1,
        durasi: +(t1 - t0).toFixed(2),
        _count: 1,
      }
      aktif.set(key, merged)
      hasil.push(merged)
    }
  }

  // Terurut menaik by t0 (hasil.push mengikuti urutan sorted, tapi jaminan eksplisit).
  return hasil.sort((a, b) => a.t0 - b.t0)
}

export default dedupeEvents
