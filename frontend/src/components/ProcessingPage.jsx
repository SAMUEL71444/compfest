/* ─────────────────────────────────────────────────────────────────────────────
   ProcessingPage — halaman loading saat backend menganalisis video
   Desain: latar kertas hangat, kerangka animasi berjalan dengan warna sigap
───────────────────────────────────────────────────────────────────────────── */

/* Siluet kerangka yang berjalan — bergerak dengan SVG animateTransform */
function WalkingSkeleton() {
  return (
    <svg
      width="96" height="116"
      viewBox="0 0 96 116"
      fill="none"
      aria-hidden="true"
      style={{ animation: 'skeletonGlow 2.5s ease-in-out infinite' }}
    >
      {/* Kepala */}
      <circle cx="48" cy="14" r="10" stroke="var(--sigap)" strokeWidth="2.5" />

      {/* Badan */}
      <line x1="48" y1="24" x2="48" y2="62" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round" />

      {/* Lengan kiri — berayun ke depan */}
      <g>
        <line x1="48" y1="36" x2="26" y2="50" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate"
            values="-18,48,36;12,48,36;-18,48,36" dur="1.1s" repeatCount="indefinite" />
        </line>
        <line x1="26" y1="50" x2="16" y2="65" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate"
            values="-18,48,36;12,48,36;-18,48,36" dur="1.1s" repeatCount="indefinite" />
        </line>
      </g>

      {/* Lengan kanan — berayun ke belakang */}
      <g>
        <line x1="48" y1="36" x2="70" y2="50" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate"
            values="12,48,36;-18,48,36;12,48,36" dur="1.1s" repeatCount="indefinite" />
        </line>
        <line x1="70" y1="50" x2="80" y2="65" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate"
            values="12,48,36;-18,48,36;12,48,36" dur="1.1s" repeatCount="indefinite" />
        </line>
      </g>

      {/* Kaki kiri */}
      <g>
        <line x1="48" y1="62" x2="36" y2="88" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate"
            values="-22,48,62;16,48,62;-22,48,62" dur="1.1s" repeatCount="indefinite" />
        </line>
        <line x1="36" y1="88" x2="34" y2="108" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate"
            values="-22,48,62;16,48,62;-22,48,62" dur="1.1s" repeatCount="indefinite" />
        </line>
      </g>

      {/* Kaki kanan */}
      <g>
        <line x1="48" y1="62" x2="60" y2="88" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate"
            values="16,48,62;-22,48,62;16,48,62" dur="1.1s" repeatCount="indefinite" />
        </line>
        <line x1="60" y1="88" x2="62" y2="108" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate"
            values="16,48,62;-22,48,62;16,48,62" dur="1.1s" repeatCount="indefinite" />
        </line>
      </g>

      {/* Titik sendi */}
      {[
        [48, 24], [26, 50], [70, 50], [16, 65], [80, 65],
        [36, 88], [60, 88], [34, 108], [62, 108],
      ].map(([cx, cy], i) => (
        <circle key={i} cx={cx} cy={cy} r="3.5" fill="var(--sigap)" opacity="0.85" />
      ))}
    </svg>
  )
}

/* Langkah-langkah pipeline yang ditampilkan saat loading */
const STEPS = [
  { label: 'Mendeteksi pose per frame dengan YOLOv8' },
  { label: 'Normalisasi & windowing sekuens keypoint' },
  { label: 'Inferensi BiLSTM — jatuh & interaksi rak' },
  { label: 'Verifikasi geometri: sudut torso & diam' },
  { label: 'Merender video beranotasi (kerangka sendi)' },
]

export default function ProcessingPage({ onCancel }) {
  return (
    <main
      className="page-center page-enter"
      style={{ maxWidth: 560, width: '100%', margin: '0 auto', gap: 0 }}
    >
      {/* ── Figur kerangka berjalan ──────────────────────────────────── */}
      <div style={{ marginBottom: 32, position: 'relative', display: 'inline-block' }}>
        <WalkingSkeleton />
        {/* Lingkaran orbit tipis */}
        <div style={{
          position: 'absolute',
          top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)',
          width: 168, height: 168,
          borderRadius: '50%',
          border: '1.5px solid rgba(47, 107, 88, 0.14)',
          animation: 'spin 10s linear infinite',
          pointerEvents: 'none',
        }} />
        <div style={{
          position: 'absolute',
          top: '50%', left: '50%',
          transform: 'translate(-50%, -50%)',
          width: 210, height: 210,
          borderRadius: '50%',
          border: '1px solid rgba(47, 107, 88, 0.07)',
          animation: 'spin 16s linear infinite reverse',
          pointerEvents: 'none',
        }} />
      </div>

      {/* ── Judul ────────────────────────────────────────────────────── */}
      <h2 style={{
        fontFamily: "'Plus Jakarta Sans', sans-serif",
        fontSize: 24,
        fontWeight: 800,
        marginBottom: 10,
        color: 'var(--ink)',
        textAlign: 'center',
        letterSpacing: '-0.02em',
      }}>
        Sedang Menganalisis Video
      </h2>
      <p style={{
        color: 'var(--ink-soft)',
        fontSize: 14,
        marginBottom: 36,
        textAlign: 'center',
        maxWidth: 400,
        lineHeight: 1.65,
      }}>
        Proses berjalan di server — harap tunggu tanpa menutup halaman ini.
        Klip ~1 menit biasanya selesai dalam <strong style={{ color: 'var(--ink)' }}>1–3 menit</strong>.
      </p>

      {/* ── Progress bar ─────────────────────────────────────────────── */}
      <div className="progress-track" style={{ marginBottom: 32 }}>
        <div className="progress-sweep" />
      </div>

      {/* ── Langkah pipeline ─────────────────────────────────────────── */}
      <div
        className="card"
        style={{ width: '100%', padding: '8px 20px', marginBottom: 32 }}
      >
        {STEPS.map((step, i) => (
          <div key={i} className="process-step">
            {/* Nomor langkah */}
            <div style={{
              width: 22, height: 22,
              borderRadius: '50%',
              background: 'var(--sigap-soft)',
              color: 'var(--sigap-dark)',
              fontSize: 11,
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
              fontFamily: "'IBM Plex Mono', monospace",
            }}>
              {String(i + 1).padStart(2, '0')}
            </div>
            <span style={{ fontSize: 13, color: 'var(--ink-soft)', lineHeight: 1.5 }}>
              {step.label}
            </span>
            {/* Dot berkedip */}
            <div
              className="process-step-dot"
              style={{
                animation: `pulse ${1.4 + i * 0.25}s ease-in-out infinite`,
                animationDelay: `${i * 0.18}s`,
              }}
            />
          </div>
        ))}
      </div>

      {/* ── Tombol batal ─────────────────────────────────────────────── */}
      <button
        id="cancel-analysis-btn"
        type="button"
        className="btn btn-ghost"
        onClick={onCancel}
        style={{ fontSize: 14 }}
      >
        Batalkan
      </button>
    </main>
  )
}
