import { useState, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'

/* ─────────────────────────────────────────────────────────────────────────────
   StatistikPage — laporan penanganan untuk manajer/pemilik toko.

   Sumber data: GET /api/statistik → backend merangkum penanganan.jsonl (permanen).
   Berbeda dari statistik sesi Live (yang sementara di browser), halaman ini
   membaca catatan permanen di server, jadi bertahan lintas sesi & bisa dibuka
   kapan saja.

   Metrik mengukur respons TIM. Nama staf muncul dari konfirmasi via Telegram
   (staf berkontrak, bukan pelanggan) — pelanggan tetap anonim (wajah diblur).
───────────────────────────────────────────────────────────────────────────── */

const POLL_MS = 8000

function formatDetik(d) {
  if (d == null) return '—'
  return `${d.toFixed(1)} dtk`
}

function waktuJam(epoch) {
  if (!epoch) return '—'
  return new Date(epoch * 1000).toLocaleString('id-ID', {
    day: '2-digit', month: 'short', hour: '2-digit', minute: '2-digit',
  })
}

const STATUS_META = {
  ditangani:   { label: 'Ditangani',   warna: 'var(--sigap)',      bg: 'var(--sigap-soft)' },
  alarm_palsu: { label: 'Alarm Palsu', warna: 'var(--ink-faint)',  bg: 'var(--paper-3)' },
  terlewat:    { label: 'Terlewat',    warna: 'var(--waspada)',    bg: 'var(--waspada-soft)' },
  menunggu:    { label: 'Menunggu',    warna: 'var(--bantu)',      bg: 'var(--bantu-soft)' },
}

/* Kartu KPI angka besar */
function KPI({ label, nilai, satuan, warna }) {
  return (
    <div style={{
      flex: '1 1 160px', minWidth: 150,
      background: 'var(--surface)', border: '1px solid var(--garis)',
      borderRadius: 'var(--radius-lg)', padding: '20px 22px',
      boxShadow: 'var(--shadow-xs)', borderTop: `3px solid ${warna || 'var(--garis)'}`,
    }}>
      <div style={{
        fontSize: 11, fontWeight: 700, color: 'var(--ink-faint)',
        letterSpacing: '0.07em', textTransform: 'uppercase', marginBottom: 8,
      }}>{label}</div>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 6 }}>
        <span className="font-display" style={{
          fontSize: 42, fontWeight: 600, color: warna || 'var(--ink)', lineHeight: 1,
        }}>{nilai}</span>
        {satuan && <span style={{ fontSize: 13, color: 'var(--ink-faint)' }}>{satuan}</span>}
      </div>
    </div>
  )
}

export default function StatistikPage() {
  const navigate = useNavigate()
  const [data, setData] = useState(null)
  const [galat, setGalat] = useState('')
  const [rentang, setRentang] = useState('semua')   // 'hari' | '7hari' | 'semua'
  const [saring, setSaring]   = useState('semua')   // 'semua' | status
  const [urut, setUrut]       = useState('baru')    // 'baru' | 'lama' | 'respons'
  const [menghapus, setMenghapus] = useState(false)

  const ambil = useCallback(async () => {
    try {
      const res = await fetch('/api/statistik')
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      setData(await res.json())
      setGalat('')
    } catch {
      setGalat('Tidak bisa memuat statistik. Pastikan backend berjalan.')
    }
  }, [])

  useEffect(() => {
    ambil()
    const id = setInterval(ambil, POLL_MS)
    return () => clearInterval(id)
  }, [ambil])

  // Hapus seluruh histori (destruktif) — dengan konfirmasi.
  async function hapusHistori() {
    if (!window.confirm('Hapus SEMUA histori penanganan? Tindakan ini permanen dan tidak bisa dibatalkan.')) return
    setMenghapus(true)
    try {
      const res = await fetch('/api/statistik', { method: 'DELETE' })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      await ambil()
    } catch {
      setGalat('Gagal menghapus histori.')
    } finally {
      setMenghapus(false)
    }
  }

  // Filter + sort riwayat di sisi frontend (tidak menyentuh file backend).
  const riwayatTampil = useMemo(() => {
    if (!data?.riwayat) return []
    const now = Date.now() / 1000
    const ambangRentang = rentang === 'hari' ? 86400 : rentang === '7hari' ? 7 * 86400 : Infinity
    let arr = data.riwayat.filter(r => {
      if (saring !== 'semua' && r.status !== saring) return false
      if (ambangRentang !== Infinity && (now - (r.t_muncul || 0)) > ambangRentang) return false
      return true
    })
    arr = [...arr]
    if (urut === 'baru')     arr.sort((a, b) => (b.t_muncul || 0) - (a.t_muncul || 0))
    else if (urut === 'lama') arr.sort((a, b) => (a.t_muncul || 0) - (b.t_muncul || 0))
    else if (urut === 'respons') arr.sort((a, b) => (b.respons_detik ?? -1) - (a.respons_detik ?? -1))
    return arr
  }, [data, rentang, saring, urut])

  const kosong = data && data.total === 0

  const selStyle = {
    fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
    padding: '5px 10px', borderRadius: 20, cursor: 'pointer',
    background: 'var(--surface)', color: 'var(--ink-soft)',
    border: '1px solid var(--garis)',
  }

  return (
    <div className="page-container" style={{ background: 'var(--paper)' }}>
      {/* ── Navbar ─────────────────────────────────────────────────────── */}
      <nav className="navbar">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {/* Tombol kembali eksplisit */}
          <button
            onClick={() => navigate('/')}
            aria-label="Kembali ke halaman utama"
            style={{
              display: 'inline-flex', alignItems: 'center', gap: 6,
              background: 'rgba(255,255,255,0.14)',
              border: '1.5px solid rgba(255,255,255,0.28)',
              borderRadius: 50, color: 'white',
              fontSize: 13, fontWeight: 600,
              padding: '6px 14px 6px 10px',
              cursor: 'pointer', fontFamily: 'inherit',
              transition: 'background 150ms',
            }}
            onMouseOver={e => e.currentTarget.style.background = 'rgba(255,255,255,0.24)'}
            onMouseOut={e => e.currentTarget.style.background = 'rgba(255,255,255,0.14)'}
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" aria-hidden="true">
              <path d="M9 2L4 7l5 5" stroke="white" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
            Home
          </button>

          <button className="navbar-brand" onClick={() => navigate('/')}
            style={{ cursor: 'pointer', background: 'none', border: 'none', padding: 0 }}
            aria-label="Kembali ke halaman utama">
            <div className="navbar-logo">
              <img src="/sapa.png" alt="SAPA Logo" />
            </div>
            <div>
              <div className="navbar-title">SAPA</div>
              <div className="navbar-subtitle">Laporan Penanganan</div>
            </div>
          </button>
        </div>
        <div className="navbar-badge">Metrik Tim · Privacy-by-Design</div>
      </nav>

      <main style={{ flex: 1, maxWidth: 1100, width: '100%', margin: '0 auto', padding: '32px 20px 60px' }}>
        <div style={{ marginBottom: 28 }}>
          <h1 style={{ fontSize: 28, fontWeight: 800, color: 'var(--ink)', letterSpacing: '-0.03em', marginBottom: 6 }}>
            Laporan Penanganan
          </h1>
          <p style={{ color: 'var(--ink-soft)', fontSize: 14, maxWidth: 620, lineHeight: 1.6 }}>
            Rekap kejadian yang ditandai SAPA dan bagaimana tim toko meresponsnya.
            Data bertahan permanen — tidak hilang saat sesi pemantauan ditutup.
          </p>
        </div>

        {galat && (
          <div className="error-banner" style={{ marginBottom: 20 }} role="alert">
            <span>⚠ {galat}</span>
          </div>
        )}

        {!data && !galat && (
          <div style={{ padding: 60, textAlign: 'center', color: 'var(--ink-faint)' }}>
            Memuat statistik…
          </div>
        )}

        {data && (
          <>
            {/* ── KPI ─────────────────────────────────────────────────── */}
            <div style={{ display: 'flex', gap: 14, flexWrap: 'wrap', marginBottom: 16 }}>
              <KPI label="Total kejadian" nilai={data.total} warna="var(--ink)" />
              <KPI label="Ditangani" nilai={data.ditangani} warna="var(--sigap)" />
              <KPI label="Alarm palsu" nilai={data.alarm_palsu} warna="var(--ink-faint)" />
              <KPI label="Terlewat" nilai={data.terlewat} warna="var(--waspada)" />
              <KPI label="Rata-rata respons" nilai={data.rata_respons_detik ?? '—'}
                satuan={data.rata_respons_detik != null ? 'dtk' : ''} warna="var(--bantu)" />
            </div>

            <div style={{ fontSize: 12, color: 'var(--ink-faint)', marginBottom: 28 }}>
              Batas "terlewat": kejadian tak dikonfirmasi dalam{' '}
              {Math.round(data.batas_terlewat_detik)} detik.
            </div>

            {kosong ? (
              <div style={{
                padding: '48px 24px', textAlign: 'center',
                background: 'var(--surface)', border: '1px dashed var(--ink-hairline)',
                borderRadius: 'var(--radius-lg)', color: 'var(--ink-soft)',
              }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>Belum ada data penanganan</div>
                <div style={{ fontSize: 13, color: 'var(--ink-faint)', lineHeight: 1.6 }}>
                  Statistik akan muncul setelah ada kejadian di mode Live dan tim mulai
                  meresponsnya (lewat tombol di Telegram atau dashboard).
                </div>
              </div>
            ) : (
              <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0,1fr) minmax(0,1.2fr)', gap: 24, alignItems: 'start' }}>
                {/* ── Peringkat staf ─────────────────────────────────── */}
                <section>
                  <h2 style={{
                    fontSize: 12, fontWeight: 700, color: 'var(--ink-soft)',
                    letterSpacing: '0.07em', textTransform: 'uppercase', marginBottom: 12,
                  }}>Penanganan per Staf</h2>

                  <div style={{
                    background: 'var(--surface)', border: '1px solid var(--garis)',
                    borderRadius: 'var(--radius-lg)', overflow: 'hidden',
                  }}>
                    {data.peringkat_staf.length === 0 ? (
                      <div style={{ padding: '28px 20px', textAlign: 'center', color: 'var(--ink-faint)', fontSize: 13 }}>
                        Belum ada penanganan tercatat.
                      </div>
                    ) : data.peringkat_staf.map((s, i) => (
                      <div key={s.nama} style={{
                        display: 'flex', alignItems: 'center', gap: 12,
                        padding: '12px 16px',
                        borderBottom: i < data.peringkat_staf.length - 1 ? '1px solid var(--garis-soft)' : 'none',
                      }}>
                        <span style={{
                          width: 26, height: 26, borderRadius: '50%',
                          background: i === 0 ? 'var(--sigap)' : 'var(--paper-3)',
                          color: i === 0 ? '#fff' : 'var(--ink-soft)',
                          display: 'flex', alignItems: 'center', justifyContent: 'center',
                          fontSize: 12, fontWeight: 700, flexShrink: 0,
                        }}>{i + 1}</span>
                        <div style={{ flex: 1, minWidth: 0 }}>
                          <div style={{ fontWeight: 700, fontSize: 14, color: 'var(--ink)' }}>{s.nama}</div>
                          <div style={{ fontSize: 12, color: 'var(--ink-faint)' }}>
                            rata-rata respons {formatDetik(s.rata_respons)}
                          </div>
                        </div>
                        <div style={{ textAlign: 'right' }}>
                          <div className="font-display" style={{ fontSize: 22, fontWeight: 600, color: 'var(--sigap)', lineHeight: 1 }}>
                            {s.ditangani}
                          </div>
                          <div style={{ fontSize: 10.5, color: 'var(--ink-faint)' }}>ditangani</div>
                        </div>
                      </div>
                    ))}
                  </div>

                  <div style={{ fontSize: 11, color: 'var(--ink-faint)', marginTop: 10, lineHeight: 1.6 }}>
                    Nama berasal dari staf yang menekan "Saya Tangani" di Telegram.
                    Wajah pelanggan tetap tidak dikenali.
                  </div>
                </section>

                {/* ── Riwayat ────────────────────────────────────────── */}
                <section>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12, gap: 10, flexWrap: 'wrap' }}>
                    <h2 style={{
                      fontSize: 12, fontWeight: 700, color: 'var(--ink-soft)',
                      letterSpacing: '0.07em', textTransform: 'uppercase', margin: 0,
                    }}>Riwayat Kejadian</h2>
                    <button
                      type="button"
                      onClick={hapusHistori}
                      disabled={menghapus}
                      style={{
                        fontSize: 11.5, fontWeight: 600, fontFamily: 'inherit',
                        padding: '5px 12px', borderRadius: 20, cursor: 'pointer',
                        background: 'var(--waspada-soft)', color: 'var(--waspada-dark)',
                        border: '1px solid var(--waspada-border)',
                      }}
                    >
                      {menghapus ? 'Menghapus…' : '🗑 Hapus Histori'}
                    </button>
                  </div>

                  {/* Kontrol filter + sort */}
                  <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginBottom: 10 }}>
                    <select value={rentang} onChange={e => setRentang(e.target.value)} style={selStyle}>
                      <option value="hari">Hari ini</option>
                      <option value="7hari">7 hari</option>
                      <option value="semua">Semua waktu</option>
                    </select>
                    <select value={saring} onChange={e => setSaring(e.target.value)} style={selStyle}>
                      <option value="semua">Semua status</option>
                      <option value="ditangani">Ditangani</option>
                      <option value="alarm_palsu">Alarm palsu</option>
                      <option value="terlewat">Terlewat</option>
                      <option value="menunggu">Menunggu</option>
                    </select>
                    <select value={urut} onChange={e => setUrut(e.target.value)} style={selStyle}>
                      <option value="baru">Terbaru dulu</option>
                      <option value="lama">Terlama dulu</option>
                      <option value="respons">Waktu respons</option>
                    </select>
                  </div>

                  <div style={{
                    background: 'var(--surface)', border: '1px solid var(--garis)',
                    borderRadius: 'var(--radius-lg)', overflow: 'hidden',
                    maxHeight: 520, overflowY: 'auto',
                  }}>
                    {riwayatTampil.length === 0 && (
                      <div style={{ padding: '24px', textAlign: 'center', color: 'var(--ink-faint)', fontSize: 13 }}>
                        Tidak ada kejadian untuk filter ini.
                      </div>
                    )}
                    {riwayatTampil.map((r) => {
                      const meta = STATUS_META[r.status] || STATUS_META.menunggu
                      const isFall = r.tipe === 'jatuh'
                      return (
                        <div key={r.id} style={{
                          padding: '11px 16px', borderBottom: '1px solid var(--garis-soft)',
                          borderLeft: `3px solid ${isFall ? 'var(--waspada)' : 'var(--bantu)'}`,
                        }}>
                          <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'baseline' }}>
                            <span style={{ fontSize: 13, fontWeight: 700, color: isFall ? 'var(--waspada)' : 'var(--bantu)' }}>
                              {isFall ? 'Jatuh' : 'Butuh Bantuan'}
                            </span>
                            <span className="chip" style={{ background: meta.bg, color: meta.warna }}>
                              {meta.label}
                            </span>
                          </div>
                          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 5, fontSize: 11.5, color: 'var(--ink-faint)', fontFamily: "'JetBrains Mono', monospace" }}>
                            <span>Orang #{r.track_id ?? '?'}</span>
                            <span>{waktuJam(r.t_muncul)}</span>
                            {r.respons_detik != null && <span>respons {r.respons_detik} dtk</span>}
                            {r.oleh && <span style={{ color: 'var(--sigap)' }}>oleh {r.oleh}</span>}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </section>
              </div>
            )}

            {/* ── Prinsip ─────────────────────────────────────────────── */}
            <div className="info-box" style={{ marginTop: 28 }}>
              SAPA mengukur kesigapan <strong>tim</strong>, bukan menilai individu secara
              otomatis. Angka di sini membantu manajer memahami respons toko —
              keputusan tetap di tangan manusia.
            </div>
          </>
        )}
      </main>
    </div>
  )
}
