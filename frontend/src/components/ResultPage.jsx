import { useRef, useState, useMemo } from 'react'
import { dedupeEvents, eventId } from '../utils/dedupeEvents.js'
import KartuKejadian from './KartuKejadian.jsx'

/* ─────────────────────────────────────────────────────────────────────────────
   ResultPage — video beranotasi + timeline kejadian terpadu + ringkasan.

   Fokus: DEMO untuk juri — menampilkan hasil dengan bersih. TIDAK ada aksi
   operasional (ditangani/alarm palsu) di sini; aksi itu milik mode Live.
───────────────────────────────────────────────────────────────────────────── */

/* Badge ringkasan statistik — angka besar */
function SummaryBadge({ count, type }) {
  const isFall = type === 'jatuh'
  const label  = isFall ? 'Jatuh terdeteksi' : 'Tampak butuh bantuan'
  const icon   = isFall
    ? (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <path d="M10 3L3 15h14L10 3z" stroke="var(--waspada)" strokeWidth="1.8" strokeLinejoin="round" fill="none" />
        <line x1="10" y1="9"  x2="10" y2="12" stroke="var(--waspada)" strokeWidth="1.8" strokeLinecap="round" />
        <circle cx="10" cy="13.5" r="0.9" fill="var(--waspada)" />
      </svg>
    )
    : (
      <svg width="20" height="20" viewBox="0 0 20 20" fill="none" aria-hidden="true">
        <circle cx="10" cy="6"  r="3" stroke="var(--bantu)" strokeWidth="1.8" />
        <line x1="10" y1="9" x2="10" y2="15" stroke="var(--bantu)" strokeWidth="1.8" strokeLinecap="round" />
        <line x1="10" y1="12" x2="6"  y2="14" stroke="var(--bantu)" strokeWidth="1.8" strokeLinecap="round" />
        <line x1="10" y1="12" x2="14" y2="14" stroke="var(--bantu)" strokeWidth="1.8" strokeLinecap="round" />
      </svg>
    )

  return (
    <div className={`summary-badge ${isFall ? 'jatuh' : 'bantu'}`}>
      <span>{icon}</span>
      <div className="number font-display">{count}</div>
      <div style={{ fontSize: 12, color: 'var(--ink-soft)', textAlign: 'center', lineHeight: 1.4 }}>
        {label}
      </div>
    </div>
  )
}

/* Bangun ringkasan naratif satu kalimat dari data (setelah dedup). */
function bangunRingkasan(events) {
  const nJatuh = events.filter(e => e.tipe === 'jatuh').length
  const nBantu = events.filter(e => e.tipe === 'butuh_bantuan').length
  const total = nJatuh + nBantu
  if (total === 0) return null

  const bagian = []
  if (nJatuh > 0) bagian.push(`${nJatuh} kejadian jatuh`)
  if (nBantu > 0) {
    const nAktif = events.filter(e => e.tipe === 'butuh_bantuan' && e.sinyal === 'aktif').length
    let frasa = `${nBantu} pelanggan tampak butuh bantuan`
    if (nAktif > 0) {
      frasa += ` (${nAktif} di antaranya mengangkat tangan meminta bantuan)`
    }
    bagian.push(frasa)
  }

  return `Ditemukan ${total} kejadian yang perlu perhatian: ${bagian.join(' dan ')}.`
}

export default function ResultPage({ result, onReset }) {
  const videoRef = useRef(null)
  const [activeId, setActiveId] = useState(null)
  const [videoError, setVideoError] = useState(false)
  const [urutan, setUrutan] = useState('waktu')      // 'waktu' | 'prioritas'
  const [filter, setFilter] = useState('semua')      // 'semua' | 'jatuh' | 'butuh_bantuan'

  const { timeline = [], summary = {}, annotated_video_url, video, fps, model_mode = {} } = result

  // Dedup dulu SEBELUM render — satu peristiwa = satu kartu.
  const merged = useMemo(() => dedupeEvents(timeline), [timeline])

  // Hitung ulang ringkasan & jumlah dari data yang sudah di-dedup (bukan summary
  // backend, karena summary menghitung event mentah per-window).
  const nJatuh = merged.filter(e => e.tipe === 'jatuh').length
  const nBantu = merged.filter(e => e.tipe === 'butuh_bantuan').length
  const ringkasan = useMemo(() => bangunRingkasan(merged), [merged])

  // Filter berdasarkan tipe.
  const terfilter = useMemo(() => {
    if (filter === 'semua') return merged
    return merged.filter(e => e.tipe === filter)
  }, [merged, filter])

  // Urutkan.
  const tampil = useMemo(() => {
    const arr = [...terfilter]
    if (urutan === 'prioritas') {
      // Jatuh di atas semua, lalu butuh_bantuan; masing-masing sub-sort by t0.
      arr.sort((a, b) => {
        const pa = a.tipe === 'jatuh' ? 0 : 1
        const pb = b.tipe === 'jatuh' ? 0 : 1
        if (pa !== pb) return pa - pb
        return a.t0 - b.t0
      })
    } else {
      arr.sort((a, b) => a.t0 - b.t0)
    }
    return arr
  }, [terfilter, urutan])

  // Cache-buster stabil: dihitung SEKALI per hasil, bukan tiap render.
  // Sebelumnya Date.now() dievaluasi ulang setiap render → string src berubah
  // terus → <video> reload berulang & sempat memicu onError palsu.
  // encodeURI menangani nama file dengan spasi / tanda kurung.
  const videoSrc = useMemo(() => {
    if (!annotated_video_url) return annotated_video_url
    const ts = result._ts ?? Date.now()
    if (!annotated_video_url.startsWith('/')) return annotated_video_url
    return `${encodeURI(annotated_video_url)}?t=${ts}`
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [annotated_video_url, result._ts])

  function seekTo(t0, id) {
    setActiveId(id)
    if (videoRef.current) {
      videoRef.current.currentTime = t0
      videoRef.current.play().catch(() => {})
    }
  }

  const hasEvents = merged.length > 0

  function ModelChip({ active, label }) {
    return (
      <span style={{
        display: 'inline-flex', alignItems: 'center', gap: 5,
        fontSize: 11, fontWeight: 600, fontFamily: "'JetBrains Mono', monospace",
        padding: '3px 10px', borderRadius: 20,
        background: active ? 'rgba(44,93,75,0.10)' : 'rgba(26,28,24,0.04)',
        color: active ? 'var(--sigap)' : 'var(--ink-faint)',
        border: `1px solid ${active ? 'rgba(44,93,75,0.25)' : 'var(--garis)'}`,
      }}>
        <span style={{
          width: 5, height: 5, borderRadius: '50%',
          background: active ? 'var(--sigap)' : 'var(--ink-faint)',
          display: 'inline-block',
        }} />
        {label}
      </span>
    )
  }

  /* Tombol toggle kecil (urutan & filter) */
  function Segmen({ opsi, nilai, onPilih }) {
    return (
      <div style={{
        display: 'inline-flex', gap: 4, padding: 4,
        background: 'var(--surface)', border: '1px solid var(--garis)',
        borderRadius: 999,
      }}>
        {opsi.map(o => {
          const aktif = nilai === o.id
          return (
            <button
              key={o.id}
              type="button"
              onClick={() => onPilih(o.id)}
              style={{
                padding: '5px 14px', borderRadius: 999, border: 'none',
                fontSize: 12, fontWeight: 600, fontFamily: 'inherit',
                cursor: 'pointer',
                background: aktif ? 'var(--sigap-soft)' : 'transparent',
                color: aktif ? 'var(--sigap-dark)' : 'var(--ink-soft)',
                transition: 'all var(--dur-fast) var(--ease)',
              }}
            >
              {o.label}
            </button>
          )
        })}
      </div>
    )
  }

  return (
    <main
      className="page-enter"
      style={{ width: '100%', maxWidth: 1200, margin: '0 auto', padding: '36px 20px 60px' }}
    >
      {/* ── Header ────────────────────────────────────────────────────── */}
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
        marginBottom: 24, flexWrap: 'wrap', gap: 16,
      }}>
        <div>
          <h1 style={{ fontSize: 28, fontWeight: 800, marginBottom: 5, color: 'var(--ink)', letterSpacing: '-0.03em' }}>
            Hasil Analisis
          </h1>
          <div style={{
            fontSize: 13, color: 'var(--ink-faint)',
            fontFamily: "'JetBrains Mono', monospace", letterSpacing: '0.02em', marginBottom: 10,
          }}>
            {video} · {fps?.toFixed(1) || '?'} fps
          </div>
          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
            <ModelChip active={model_mode.fall}        label="Deteksi Jatuh" />
            <ModelChip active={model_mode.interaction} label="Deteksi Interaksi" />
          </div>
        </div>
        <button
          id="analyze-again-btn"
          type="button"
          className="btn btn-ghost"
          onClick={onReset}
          style={{ fontSize: 14 }}
        >
          ← Analisis Video Baru
        </button>
      </div>

      {/* ── Ringkasan naratif otomatis ─────────────────────────────────── */}
      {ringkasan && (
        <div style={{
          marginBottom: 20, padding: '14px 20px',
          borderRadius: 'var(--radius-md)',
          background: 'var(--paper-2)', border: '1px solid var(--garis)',
          fontSize: 14, color: 'var(--ink)', lineHeight: 1.6,
        }}>
          {ringkasan}
        </div>
      )}

      {/* ── Ringkasan statistik ────────────────────────────────────────── */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 32, flexWrap: 'wrap' }}>
        <SummaryBadge count={nJatuh} type="jatuh"  />
        <SummaryBadge count={nBantu} type="bantuan" />

        {/* Edge state: timeline kosong → kartu NETRAL, jujur dua kemungkinan */}
        {!hasEvents && (
          <div style={{
            flex: '1 1 0', minWidth: 200, padding: '20px 24px',
            borderRadius: 'var(--radius-lg)',
            background: 'var(--paper-2)', border: '1px solid var(--garis)',
            display: 'flex', alignItems: 'center', gap: 14,
          }}>
            <svg width="28" height="28" viewBox="0 0 28 28" fill="none" aria-hidden="true">
              <circle cx="14" cy="14" r="12" stroke="var(--ink-faint)" strokeWidth="1.8" />
              <line x1="14" y1="9" x2="14" y2="15" stroke="var(--ink-faint)" strokeWidth="1.8" strokeLinecap="round" />
              <circle cx="14" cy="19" r="0.9" fill="var(--ink-faint)" />
            </svg>
            <div>
              <div style={{ fontWeight: 700, marginBottom: 3, color: 'var(--ink)', fontSize: 14 }}>
                Tidak ada kejadian terdeteksi
              </div>
              <div style={{ fontSize: 13, color: 'var(--ink-soft)', lineHeight: 1.55 }}>
                Ini bisa berarti tidak ada insiden yang perlu perhatian, atau tidak
                ada orang di area kamera pada rekaman ini.
              </div>
            </div>
          </div>
        )}

        {summary.total_track > 0 && (
          <div style={{
            padding: '20px 24px', borderRadius: 'var(--radius-lg)',
            background: 'var(--surface)', border: '1px solid var(--garis)',
            display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 6, minWidth: 110,
          }}>
            <div className="font-display" style={{ fontSize: 40, fontWeight: 600, color: 'var(--ink)', lineHeight: 1 }}>
              {summary.total_track}
            </div>
            <div style={{ fontSize: 12, color: 'var(--ink-soft)', textAlign: 'center' }}>
              Orang terdeteksi
            </div>
          </div>
        )}
      </div>

      {/* ── Grid: video + timeline ─────────────────────────────────────── */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: hasEvents ? '1fr 380px' : '1fr',
        gap: 24, alignItems: 'start',
      }}>
        {/* ── Video player ─────────────────────────────────────────────── */}
        <div>
          <div style={{
            borderRadius: 'var(--radius-xl)', overflow: 'hidden', background: '#1A1A1A',
            border: '1px solid var(--garis)', boxShadow: 'var(--shadow-md)', position: 'relative',
          }}>
            {!videoError ? (
              <video
                ref={videoRef}
                id="annotated-video-player"
                key={videoSrc}
                controls
                preload="metadata"
                src={videoSrc}
                style={{ width: '100%', display: 'block', maxHeight: 540 }}
                onError={() => {
                  // Hanya tandai gagal bila elemen video benar-benar punya error
                  // (bukan event transien saat src baru dipasang).
                  const el = videoRef.current
                  if (el && el.error) setVideoError(true)
                }}
              >
                Browser Anda tidak mendukung pemutar video.
              </video>
            ) : (
              <div style={{ padding: 56, textAlign: 'center', color: 'var(--ink-faint)' }}>
                <svg width="48" height="48" viewBox="0 0 48 48" fill="none" style={{ marginBottom: 14 }} aria-hidden="true">
                  <circle cx="24" cy="24" r="20" stroke="var(--garis)" strokeWidth="2" />
                  <line x1="16" y1="16" x2="32" y2="32" stroke="var(--ink-faint)" strokeWidth="2" strokeLinecap="round" />
                  <line x1="32" y1="16" x2="16" y2="32" stroke="var(--ink-faint)" strokeWidth="2" strokeLinecap="round" />
                </svg>
                <div style={{ fontSize: 14, marginBottom: 10, color: 'var(--ink-soft)' }}>
                  Video tidak bisa dimuat
                </div>
                <div style={{ display: 'flex', gap: 16, justifyContent: 'center', alignItems: 'center', flexWrap: 'wrap' }}>
                  <button
                    type="button"
                    onClick={() => setVideoError(false)}
                    style={{
                      background: 'none', border: 'none', cursor: 'pointer',
                      color: 'var(--sigap)', fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
                    }}
                  >
                    ↻ Coba lagi
                  </button>
                  <a href={videoSrc} target="_blank" rel="noopener noreferrer"
                    style={{ color: 'var(--sigap)', fontSize: 13, fontWeight: 600 }}>
                    Buka langsung di tab baru →
                  </a>
                </div>
              </div>
            )}
          </div>

          {/* Legenda warna kerangka */}
          <div style={{
            display: 'flex', gap: 16, flexWrap: 'wrap', margin: '10px 0 6px',
            fontSize: 12, color: 'var(--ink-soft)',
          }}>
            {[
              { bg: 'rgba(80,180,80,0.9)',   label: 'Hijau — gerakan normal' },
              { bg: 'rgba(240,140,30,0.95)', label: 'Oranye — tampak butuh bantuan' },
              { bg: 'rgba(210,40,40,0.95)',  label: 'Merah — jatuh terdeteksi' },
            ].map(({ bg, label }) => (
              <span key={label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                <span style={{ width: 18, height: 3, borderRadius: 99, background: bg, display: 'inline-block', flexShrink: 0 }} />
                {label}
              </span>
            ))}
          </div>

          {/* Privacy note */}
          <div className="privacy-note">
            <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
              <circle cx="6.5" cy="4" r="2.5" stroke="var(--ink-faint)" strokeWidth="1.3" />
              <line x1="6.5" y1="6.5" x2="6.5" y2="11" stroke="var(--ink-faint)" strokeWidth="1.3" strokeLinecap="round" />
              <line x1="6.5" y1="9" x2="4" y2="10.5" stroke="var(--ink-faint)" strokeWidth="1.3" strokeLinecap="round" />
              <line x1="6.5" y1="9" x2="9" y2="10.5" stroke="var(--ink-faint)" strokeWidth="1.3" strokeLinecap="round" />
            </svg>
            Video menampilkan{' '}
            <strong style={{ color: 'var(--sigap)', fontWeight: 600 }}>kerangka sendi saja</strong>{' '}
            — wajah dan identitas tidak dikenali (privacy-by-design)
          </div>
        </div>

        {/* ── Timeline terpadu ─────────────────────────────────────────── */}
        {hasEvents && (
          <div>
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 12,
            }}>
              <div style={{
                fontSize: 12, fontWeight: 700, color: 'var(--ink-soft)',
                letterSpacing: '0.07em', textTransform: 'uppercase',
              }}>
                Timeline Kejadian
              </div>
              <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: 'var(--ink-faint)' }}>
                menampilkan {tampil.length} dari {merged.length}
              </span>
            </div>

            {/* Kontrol: toggle urutan + filter tipe */}
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
              <Segmen
                nilai={urutan}
                onPilih={setUrutan}
                opsi={[
                  { id: 'waktu', label: '⏰ Waktu' },
                  { id: 'prioritas', label: '! Prioritas' },
                ]}
              />
              <Segmen
                nilai={filter}
                onPilih={setFilter}
                opsi={[
                  { id: 'semua', label: 'Semua' },
                  { id: 'jatuh', label: 'Jatuh' },
                  { id: 'butuh_bantuan', label: 'Butuh Bantuan' },
                ]}
              />
            </div>

            {/* Daftar kartu kejadian */}
            <div style={{
              display: 'flex', flexDirection: 'column', gap: 8,
              maxHeight: 490, overflowY: 'auto', paddingRight: 2,
            }}>
              {tampil.map((event) => {
                const id = eventId(event)
                return (
                  <KartuKejadian
                    key={id}
                    event={event}
                    mode="analisis"
                    active={activeId === id}
                    onSeek={(t0) => seekTo(t0, id)}
                  />
                )
              })}
              {tampil.length === 0 && (
                <div style={{ padding: '24px', textAlign: 'center', color: 'var(--ink-faint)', fontSize: 13 }}>
                  Tidak ada kejadian untuk filter ini.
                </div>
              )}
            </div>

            <div className="info-box" style={{ marginTop: 14, fontSize: 12 }}>
              Klik kartu kejadian untuk melompat ke waktu tersebut di video.
            </div>
          </div>
        )}
      </div>

      {/* ── Prinsip ───────────────────────────────────────────────────── */}
      <div style={{
        marginTop: 40, padding: '20px 24px', borderRadius: 'var(--radius-lg)',
        background: 'var(--sigap-soft)', border: '1px solid rgba(47, 107, 88, 0.18)',
        display: 'flex', alignItems: 'center', gap: 16, flexWrap: 'wrap',
      }}>
        <svg width="32" height="32" viewBox="0 0 32 32" fill="none" aria-hidden="true">
          <path d="M6 18c0 0 2-3 6-3h8c4 0 6 3 6 3" stroke="var(--sigap)" strokeWidth="1.8" strokeLinecap="round" />
          <line x1="10" y1="15" x2="10" y2="8" stroke="var(--sigap)" strokeWidth="1.8" strokeLinecap="round" />
          <line x1="14" y1="15" x2="14" y2="6" stroke="var(--sigap)" strokeWidth="1.8" strokeLinecap="round" />
          <line x1="18" y1="15" x2="18" y2="8" stroke="var(--sigap)" strokeWidth="1.8" strokeLinecap="round" />
          <line x1="22" y1="15" x2="22" y2="10" stroke="var(--sigap)" strokeWidth="1.8" strokeLinecap="round" />
          <path d="M6 18v6h20v-6" stroke="var(--sigap)" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        <div style={{ flex: 1, minWidth: 200 }}>
          <div style={{ fontWeight: 700, marginBottom: 5, fontSize: 14, color: 'var(--sigap-dark)' }}>
            "AI Menandai, Manusia Memutuskan"
          </div>
          <div style={{ fontSize: 13, color: 'var(--ink-soft)', maxWidth: 640, lineHeight: 1.6 }}>
            Hasil analisis ini adalah <em>rekomendasi bantu</em> untuk karyawan — bukan keputusan otomatis.
            Selalu verifikasi secara langsung sebelum mengambil tindakan.
          </div>
        </div>
      </div>
    </main>
  )
}
