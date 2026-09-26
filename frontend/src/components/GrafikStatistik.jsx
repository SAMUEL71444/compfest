/* ─────────────────────────────────────────────────────────────────────────────
   GrafikStatistik — visualisasi ringkas untuk halaman Laporan.
   Murni SVG (tanpa library grafik) agar ringan & tanpa dependency baru.

   Dua grafik:
   1. Donut — proporsi status penanganan (ditangani / alarm palsu / terlewat / menunggu)
   2. Bar   — jumlah kejadian per tipe (jatuh vs butuh bantuan)

   Didesain agar mudah dimengerti orang awam: ada angka besar di tengah donut,
   legenda dengan label kata (bukan hanya warna), dan persentase.
───────────────────────────────────────────────────────────────────────────── */

const WARNA = {
  ditangani:   'var(--sigap)',
  alarm_palsu: 'var(--ink-faint)',
  terlewat:    'var(--waspada)',
  menunggu:    'var(--bantu)',
}
const LABEL = {
  ditangani:   'Ditangani',
  alarm_palsu: 'Alarm palsu',
  terlewat:    'Terlewat',
  menunggu:    'Menunggu',
}

/* Donut chart dari beberapa segmen. */
function Donut({ segmen, total }) {
  const size = 168
  const stroke = 22
  const r = (size - stroke) / 2
  const keliling = 2 * Math.PI * r
  const cx = size / 2
  const cy = size / 2

  let offset = 0
  const arcs = segmen
    .filter(s => s.nilai > 0)
    .map(s => {
      const frac = total > 0 ? s.nilai / total : 0
      const len = frac * keliling
      const arc = (
        <circle
          key={s.key}
          cx={cx} cy={cy} r={r}
          fill="none"
          stroke={s.warna}
          strokeWidth={stroke}
          strokeDasharray={`${len} ${keliling - len}`}
          strokeDashoffset={-offset}
          transform={`rotate(-90 ${cx} ${cy})`}
          strokeLinecap="butt"
        />
      )
      offset += len
      return arc
    })

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Proporsi status penanganan">
      {/* Cincin dasar */}
      <circle cx={cx} cy={cy} r={r} fill="none" stroke="var(--paper-3)" strokeWidth={stroke} />
      {total > 0 ? arcs : null}
      {/* Angka total di tengah */}
      <text x={cx} y={cy - 2} textAnchor="middle" fontFamily="'Instrument Serif', Georgia, serif"
        fontSize="40" fill="var(--ink)">{total}</text>
      <text x={cx} y={cy + 20} textAnchor="middle" fontFamily="'DM Sans', sans-serif"
        fontSize="11" fill="var(--ink-faint)" letterSpacing="0.05em">KEJADIAN</text>
    </svg>
  )
}

/* Bar chart horizontal sederhana. */
function BarRow({ label, nilai, maks, warna }) {
  const pct = maks > 0 ? (nilai / maks) * 100 : 0
  return (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: 4, fontSize: 13 }}>
        <span style={{ color: 'var(--ink)', fontWeight: 600 }}>{label}</span>
        <span style={{ color: 'var(--ink-faint)', fontFamily: "'JetBrains Mono', monospace" }}>{nilai}</span>
      </div>
      <div style={{ height: 10, borderRadius: 6, background: 'var(--paper-3)', overflow: 'hidden' }}>
        <div style={{
          width: `${pct}%`, height: '100%', background: warna,
          borderRadius: 6, transition: 'width var(--dur-slow) var(--ease)',
        }} />
      </div>
    </div>
  )
}

export default function GrafikStatistik({ data }) {
  if (!data) return null

  const segmen = [
    { key: 'ditangani',   nilai: data.ditangani || 0,   warna: WARNA.ditangani,   label: LABEL.ditangani },
    { key: 'alarm_palsu', nilai: data.alarm_palsu || 0, warna: WARNA.alarm_palsu, label: LABEL.alarm_palsu },
    { key: 'terlewat',    nilai: data.terlewat || 0,    warna: WARNA.terlewat,    label: LABEL.terlewat },
    { key: 'menunggu',    nilai: data.menunggu || 0,    warna: WARNA.menunggu,    label: LABEL.menunggu },
  ]
  const total = segmen.reduce((s, x) => s + x.nilai, 0)

  // Jumlah per tipe kejadian dari riwayat.
  const nJatuh = (data.riwayat || []).filter(r => r.tipe === 'jatuh').length
  const nBantu = (data.riwayat || []).filter(r => r.tipe === 'butuh_bantuan').length
  const maksTipe = Math.max(nJatuh, nBantu, 1)

  return (
    <div style={{
      display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
      gap: 20, marginBottom: 28,
    }}>
      {/* ── Donut proporsi status ─────────────────────────────────────── */}
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--garis)',
        borderRadius: 'var(--radius-lg)', padding: '20px 22px', boxShadow: 'var(--shadow-xs)',
      }}>
        <div style={{
          fontSize: 12, fontWeight: 700, color: 'var(--ink-soft)',
          letterSpacing: '0.07em', textTransform: 'uppercase', marginBottom: 16,
        }}>Proporsi Penanganan</div>

        <div style={{ display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap' }}>
          <Donut segmen={segmen} total={total} />
          <div style={{ flex: 1, minWidth: 130 }}>
            {segmen.map(s => {
              const pct = total > 0 ? Math.round((s.nilai / total) * 100) : 0
              return (
                <div key={s.key} style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 9 }}>
                  <span style={{ width: 12, height: 12, borderRadius: 3, background: s.warna, flexShrink: 0 }} />
                  <span style={{ fontSize: 13, color: 'var(--ink)', flex: 1 }}>{s.label}</span>
                  <span style={{ fontSize: 13, fontWeight: 700, color: 'var(--ink)' }}>{s.nilai}</span>
                  <span style={{ fontSize: 11, color: 'var(--ink-faint)', width: 34, textAlign: 'right' }}>{pct}%</span>
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* ── Bar per tipe kejadian ─────────────────────────────────────── */}
      <div style={{
        background: 'var(--surface)', border: '1px solid var(--garis)',
        borderRadius: 'var(--radius-lg)', padding: '20px 22px', boxShadow: 'var(--shadow-xs)',
      }}>
        <div style={{
          fontSize: 12, fontWeight: 700, color: 'var(--ink-soft)',
          letterSpacing: '0.07em', textTransform: 'uppercase', marginBottom: 16,
        }}>Jenis Kejadian</div>

        <BarRow label="🚨 Jatuh" nilai={nJatuh} maks={maksTipe} warna="var(--waspada)" />
        <BarRow label="🙋 Butuh bantuan" nilai={nBantu} maks={maksTipe} warna="var(--bantu)" />

        <div style={{
          marginTop: 16, paddingTop: 14, borderTop: '1px solid var(--garis-soft)',
          display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
        }}>
          <span style={{ fontSize: 12, color: 'var(--ink-soft)' }}>Rata-rata waktu respons</span>
          <span style={{ fontSize: 20, fontWeight: 800, color: 'var(--sigap)', fontFamily: "'DM Sans', sans-serif" }}>
            {data.rata_respons_detik != null ? `${data.rata_respons_detik} dtk` : '—'}
          </span>
        </div>
      </div>
    </div>
  )
}
