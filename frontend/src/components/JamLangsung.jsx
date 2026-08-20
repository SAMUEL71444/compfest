import { useState, useEffect } from 'react'

/* ─────────────────────────────────────────────────────────────────────────────
   JamLangsung — penanda waktu yang berjalan, tampil di dalam aplikasi.

   Rulebook AIC COMPFEST 18, Ketentuan Video Proof of Work:
     "Software only: menunjukkan double screen terminal dan aplikasi serta
      timestamp. ... DILARANG KERAS memotong (cut) video atau melakukan
      editing lain."

   Timestamp itu bukti bahwa demonstrasi berlangsung menerus dan tidak dipotong.
   Menaruhnya DI DALAM aplikasi membuatnya tak terbantahkan: penonton video tidak
   perlu menafsirkan log terminal atau jam sistem operasi untuk memastikannya.

   Zona waktu dipaksa ke Asia/Jakarta supaya label "WIB" benar-benar akurat
   meski mesin perekam disetel ke zona waktu lain — deadline lomba memakai WIB,
   jadi jam yang keliru justru menimbulkan pertanyaan.
───────────────────────────────────────────────────────────────────────────── */
export default function JamLangsung({ ringkas = false }) {
  const [sekarang, setSekarang] = useState(() => new Date())

  useEffect(() => {
    // Disinkronkan ke pergantian detik agar angkanya tidak "melompat" di video.
    const keDetikBerikutnya = 1000 - (Date.now() % 1000)
    let interval
    const timeout = setTimeout(() => {
      setSekarang(new Date())
      interval = setInterval(() => setSekarang(new Date()), 1000)
    }, keDetikBerikutnya)

    return () => { clearTimeout(timeout); if (interval) clearInterval(interval) }
  }, [])

  const opsi = { timeZone: 'Asia/Jakarta', hour12: false }
  const jam = sekarang.toLocaleTimeString('id-ID', {
    ...opsi, hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
  const tanggal = sekarang.toLocaleDateString('id-ID', {
    ...opsi, day: '2-digit', month: 'short', year: 'numeric',
  })

  return (
    <div
      title="Waktu server demonstrasi (WIB)"
      style={{
        display: 'inline-flex', alignItems: 'center', gap: 8,
        background: 'rgba(255,255,255,0.12)',
        border: '1.5px solid rgba(255,255,255,0.3)',
        borderRadius: 20, padding: '5px 12px',
        fontFamily: "'JetBrains Mono', monospace",
        color: 'white', whiteSpace: 'nowrap',
      }}
    >
      {/* Titik berdenyut — penanda visual bahwa jamnya hidup, bukan gambar diam */}
      <span style={{
        width: 6, height: 6, borderRadius: '50%', background: '#7FE3B0',
        animation: 'pulse 1.5s ease-in-out infinite', display: 'inline-block',
      }} />
      {!ringkas && (
        <span style={{ fontSize: 11, opacity: 0.75 }}>{tanggal}</span>
      )}
      <span style={{ fontSize: 13, fontWeight: 700, letterSpacing: '0.04em' }}>
        {jam}
      </span>
      <span style={{ fontSize: 10, opacity: 0.65 }}>WIB</span>
    </div>
  )
}
