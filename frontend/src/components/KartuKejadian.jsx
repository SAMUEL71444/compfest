import { eventId } from '../utils/dedupeEvents.js'
import { formatRentang, formatDurasi, isTidakPasti } from '../utils/formatWaktu.js'

/* ─────────────────────────────────────────────────────────────────────────────
   KartuKejadian — kartu satu kejadian, dipakai IDENTIK di /analisis & /live.

   Props:
     event   : event (idealnya sudah lewat dedupeEvents → punya t0,t1,durasi,skor)
     mode    : "analisis" | "live"
     active  : bool — sedang di-highlight (analisis: sinkron dgn video)
     onSeek  : (t0) => void  — klik kartu lompat ke waktu (mode analisis)
     onAck   : (id) => void  — tandai "ditangani" (mode live)
     onPalsu : (id) => void  — tandai "alarm palsu" (mode live)
     onUndo  : (id) => void  — batalkan status (mode live)
     status  : "ditangani" | "palsu" | undefined  — status penanganan (mode live)
     berlangsung : bool — peristiwa masih aktif (mode live, badge "berlangsung")

   Warna semantik (design token):
     jatuh          → --waspada (merah)
     butuh_bantuan  → --bantu   (amber)
     tidak pasti    → diredam + badge abu
     ditangani      → hijau (--sigap)
     alarm palsu    → grayscale + dicoret
───────────────────────────────────────────────────────────────────────────── */

/* ── Ikon per keadaan (warna + bentuk, bukan warna saja — aksesibilitas) ── */
function IkonJatuh({ c = 'var(--waspada)' }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <path d="M9 2L2 14h14L9 2z" stroke={c} strokeWidth="1.6" strokeLinejoin="round" fill="none" />
      <line x1="9" y1="8" x2="9" y2="11" stroke={c} strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="9" cy="13" r="0.8" fill={c} />
    </svg>
  )
}

function IkonBantu({ c = 'var(--bantu)' }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <circle cx="9" cy="5" r="3" stroke={c} strokeWidth="1.6" />
      <line x1="9" y1="8" x2="9" y2="14" stroke={c} strokeWidth="1.6" strokeLinecap="round" />
      <line x1="9" y1="11" x2="5" y2="13" stroke={c} strokeWidth="1.6" strokeLinecap="round" />
      <line x1="9" y1="11" x2="13" y2="13" stroke={c} strokeWidth="1.6" strokeLinecap="round" />
      <line x1="9" y1="14" x2="7" y2="17" stroke={c} strokeWidth="1.6" strokeLinecap="round" />
      <line x1="9" y1="14" x2="11" y2="17" stroke={c} strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  )
}

function IkonTanya({ c = 'var(--ink-faint)' }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <circle cx="9" cy="9" r="7" stroke={c} strokeWidth="1.5" />
      <path d="M7 7a2 2 0 1 1 2.6 1.9c-.5.2-.9.6-.9 1.2v.4" stroke={c} strokeWidth="1.5" strokeLinecap="round" fill="none" />
      <circle cx="9" cy="13" r="0.8" fill={c} />
    </svg>
  )
}

function IkonCentang({ c = 'var(--sigap)' }) {
  return (
    <svg width="18" height="18" viewBox="0 0 18 18" fill="none" aria-hidden="true">
      <circle cx="9" cy="9" r="7" stroke={c} strokeWidth="1.5" />
      <polyline points="6,9 8,11 12,6.5" stroke={c} strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" fill="none" />
    </svg>
  )
}

export default function KartuKejadian({
  event,
  mode = 'analisis',
  active = false,
  onSeek,
  onAck,
  onPalsu,
  onUndo,
  status,
  tRespons,
  oleh,
  sumber,
  berlangsung = false,
}) {
  const id = eventId(event)
  const isFall = event.tipe === 'jatuh'
  const tidakPasti = isTidakPasti(event)
  const isPalsu = status === 'palsu'
  const isDitangani = status === 'ditangani'
  const isTerlewat = status === 'terlewat'

  const label = isFall ? 'Jatuh' : 'Butuh Bantuan'

  // Warna dasar sesuai tipe; diredam bila tidak pasti; netral bila alarm palsu.
  let warna = isFall ? 'var(--waspada)' : 'var(--bantu)'
  if (tidakPasti) warna = 'var(--ink-faint)'
  if (isPalsu) warna = 'var(--ink-faint)'
  if (isDitangani) warna = 'var(--sigap)'
  if (isTerlewat) warna = 'var(--waspada)'

  const ikon = isDitangani
    ? <IkonCentang c="var(--sigap)" />
    : tidakPasti
      ? <IkonTanya c="var(--ink-faint)" />
      : isFall
        ? <IkonJatuh c={warna} />
        : <IkonBantu c={warna} />

  const rentang = formatRentang(event.t0, event.t1)
  const durasiTxt = formatDurasi(event.durasi ?? ((event.t1 ?? event.t0) - event.t0))

  const bisaKlik = mode === 'analisis' && typeof onSeek === 'function'
  const typeClass = isFall ? 'jatuh' : 'bantu'

  // Gaya kartu — reuse .event-card dari global.css, plus override keadaan khusus.
  const gayaKartu = {
    opacity: isPalsu ? 0.55 : isDitangani ? 0.8 : 1,
    filter: isPalsu ? 'grayscale(1)' : 'none',
    borderLeftColor: warna,
    cursor: bisaKlik ? 'pointer' : 'default',
  }

  const Elemen = bisaKlik ? 'button' : 'div'

  return (
    <Elemen
      type={bisaKlik ? 'button' : undefined}
      onClick={bisaKlik ? () => onSeek(event.t0) : undefined}
      className={`event-card ${typeClass} ${active ? 'active' : ''}`}
      style={gayaKartu}
      aria-label={`${label}, orang ${event.track_id}, ${rentang}${tidakPasti ? ', tidak pasti' : ''}${isDitangani ? ', sudah ditangani' : ''}${isPalsu ? ', ditandai alarm palsu' : ''}`}
    >
      <div style={{ display: 'flex', alignItems: 'flex-start', gap: 10 }}>
        <span style={{ flexShrink: 0, marginTop: 1 }}>{ikon}</span>

        <div style={{ flex: 1, minWidth: 0 }}>
          {/* Baris label + badge keadaan */}
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap', marginBottom: 5 }}>
            <span style={{
              fontSize: 13,
              fontWeight: 700,
              color: active ? warna : 'var(--ink)',
              textDecoration: isPalsu ? 'line-through' : 'none',
              transition: 'color var(--dur-mid) var(--ease)',
            }}>
              {label}
            </span>

            {berlangsung && !status && (
              <span className="chip" style={{ background: 'rgba(26,28,24,0.06)', color: 'var(--ink-soft)' }}>
                ● berlangsung
              </span>
            )}
            {tidakPasti && !status && (
              <span className="chip" style={{ background: 'rgba(26,28,24,0.06)', color: 'var(--ink-soft)' }}>
                ? TIDAK PASTI · verifikasi manual
              </span>
            )}
            {event.sinyal === 'aktif' && !isFall && (
              <span className={`chip chip-bantu`}>ANGKAT TANGAN</span>
            )}
            {isDitangani && (
              <span className="chip chip-sigap">
                ✓ Ditangani{oleh ? ` · ${oleh}` : ''}{tRespons != null ? ` · ${tRespons.toFixed(0)} dtk` : ''}
              </span>
            )}
            {isPalsu && (
              <span className="chip" style={{ background: 'rgba(26,28,24,0.06)', color: 'var(--ink-faint)' }}>
                ⊘ Alarm Palsu
              </span>
            )}
            {isTerlewat && (
              <span className="chip chip-waspada">⏱ Terlewat (&gt;1 mnt)</span>
            )}
          </div>

          {/* Meta: orang, rentang waktu, durasi, skor */}
          <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', alignItems: 'center' }}>
            <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: 'var(--ink-faint)' }}>
              Orang #{event.track_id}
            </span>
            <span style={{
              fontFamily: "'JetBrains Mono', monospace", fontSize: 12,
              color: 'var(--ink-soft)', letterSpacing: '0.02em',
            }}>
              {rentang}
            </span>
            {durasiTxt && (
              <span style={{ fontSize: 11, color: 'var(--ink-faint)', fontFamily: "'JetBrains Mono', monospace" }}>
                {durasiTxt}
              </span>
            )}
            {event.skor != null && (
              <span className={`chip ${tidakPasti ? '' : isFall ? 'chip-waspada' : 'chip-bantu'}`}
                style={tidakPasti ? { background: 'rgba(26,28,24,0.06)', color: 'var(--ink-soft)' } : undefined}>
                {(event.skor * 100).toFixed(0)}% yakin
              </span>
            )}
          </div>

          {/* Aksi operasional — HANYA mode live */}
          {mode === 'live' && (
            <div style={{ display: 'flex', gap: 8, marginTop: 10, flexWrap: 'wrap' }}>
              {/* Belum direspons ATAU terlewat → tetap boleh ditindak (terlambat). */}
              {(!status || isTerlewat) && (
                <>
                  <button
                    type="button"
                    onClick={() => onAck?.(id)}
                    className="btn btn-outline"
                    style={{ padding: '4px 12px', fontSize: 12 }}
                  >
                    ✓ Ditangani
                  </button>
                  {!isTerlewat && (
                    <button
                      type="button"
                      onClick={() => onPalsu?.(id)}
                      className="btn btn-ghost"
                      style={{ padding: '4px 12px', fontSize: 12 }}
                    >
                      ⊘ Alarm Palsu
                    </button>
                  )}
                </>
              )}
              {status && !isTerlewat && (
                <button
                  type="button"
                  onClick={() => onUndo?.(id)}
                  className="btn btn-ghost"
                  style={{ padding: '4px 12px', fontSize: 12 }}
                >
                  ↩ Batalkan
                </button>
              )}
            </div>
          )}
        </div>

        {/* Hint klik — hanya mode analisis */}
        {bisaKlik && (
          <span style={{ fontSize: 11, color: 'var(--ink-faint)', flexShrink: 0, alignSelf: 'center' }}>
            ▶
          </span>
        )}
      </div>
    </Elemen>
  )
}
