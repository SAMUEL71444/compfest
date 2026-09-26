/* ─────────────────────────────────────────────────────────────────────────────
   formatWaktu — util format waktu bersama untuk /analisis DAN /live.
   Satu sumber kebenaran supaya tampilan waktu IDENTIK di kedua halaman.
───────────────────────────────────────────────────────────────────────────── */

// Ambang keyakinan: event dengan skor DI BAWAH ini ditandai "tidak pasti".
// Dipakai di kedua halaman (Responsible AI — sistem jujur soal keterbatasan).
export const AMBANG_YAKIN = 0.55

/** Detik → "m:ss" (mis. 75 → "1:15"). Null-safe. */
export function formatWaktu(sec) {
  if (sec == null || Number.isNaN(sec)) return '--:--'
  const m = Math.floor(sec / 60)
  const s = Math.floor(sec % 60)
  return `${m}:${String(s).padStart(2, '0')}`
}

/** Rentang "m:ss–m:ss". Bila t1 tidak ada, tampilkan t0 saja. */
export function formatRentang(t0, t1) {
  if (t1 == null || t1 === t0) return formatWaktu(t0)
  return `${formatWaktu(t0)}–${formatWaktu(t1)}`
}

/** Durasi dalam detik → "X dtk" (dibulatkan, minimal 1 dtk bila > 0). */
export function formatDurasi(detik) {
  if (detik == null || Number.isNaN(detik) || detik < 0) return null
  const d = Math.round(detik)
  return `${Math.max(d, detik > 0 ? 1 : 0)} dtk`
}

/** True bila event punya skor dan skor itu di bawah ambang keyakinan. */
export function isTidakPasti(ev) {
  return ev?.skor != null && ev.skor < AMBANG_YAKIN
}
