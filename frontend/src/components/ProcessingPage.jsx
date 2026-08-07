import { useState, useEffect } from 'react'

/* ─────────────────────────────────────────────────────────────────────────────
   ProcessingPage — halaman loading saat backend menganalisis video
───────────────────────────────────────────────────────────────────────────── */

function WalkingSkeleton() {
  return (
    <svg width="96" height="116" viewBox="0 0 96 116" fill="none" aria-hidden="true"
      style={{ animation: 'skeletonGlow 2.5s ease-in-out infinite' }}>
      <circle cx="48" cy="14" r="10" stroke="var(--sigap)" strokeWidth="2.5" />
      <line x1="48" y1="24" x2="48" y2="62" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round" />
      <g>
        <line x1="48" y1="36" x2="26" y2="50" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate" values="-18,48,36;12,48,36;-18,48,36" dur="1.1s" repeatCount="indefinite" />
        </line>
        <line x1="26" y1="50" x2="16" y2="65" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate" values="-18,48,36;12,48,36;-18,48,36" dur="1.1s" repeatCount="indefinite" />
        </line>
      </g>
      <g>
        <line x1="48" y1="36" x2="70" y2="50" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate" values="12,48,36;-18,48,36;12,48,36" dur="1.1s" repeatCount="indefinite" />
        </line>
        <line x1="70" y1="50" x2="80" y2="65" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate" values="12,48,36;-18,48,36;12,48,36" dur="1.1s" repeatCount="indefinite" />
        </line>
      </g>
      <g>
        <line x1="48" y1="62" x2="36" y2="88" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate" values="-22,48,62;16,48,62;-22,48,62" dur="1.1s" repeatCount="indefinite" />
        </line>
        <line x1="36" y1="88" x2="34" y2="108" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate" values="-22,48,62;16,48,62;-22,48,62" dur="1.1s" repeatCount="indefinite" />
        </line>
      </g>
      <g>
        <line x1="48" y1="62" x2="60" y2="88" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate" values="16,48,62;-22,48,62;16,48,62" dur="1.1s" repeatCount="indefinite" />
        </line>
        <line x1="60" y1="88" x2="62" y2="108" stroke="var(--sigap)" strokeWidth="2.5" strokeLinecap="round">
          <animateTransform attributeName="transform" type="rotate" values="16,48,62;-22,48,62;16,48,62" dur="1.1s" repeatCount="indefinite" />
        </line>
      </g>
      {[[48,24],[26,50],[70,50],[16,65],[80,65],[36,88],[60,88],[34,108],[62,108]].map(([cx,cy],i) => (
        <circle key={i} cx={cx} cy={cy} r="3.5" fill="var(--sigap)" opacity="0.85" />
      ))}
    </svg>
  )
}

const STEPS = [
  { label: 'Mendeteksi pose per frame dengan YOLOv8', durationSec: 40 },
  { label: 'Normalisasi & windowing sekuens keypoint',  durationSec: 5  },
  { label: 'Inferensi BiLSTM — jatuh & interaksi rak', durationSec: 5  },
  { label: 'Verifikasi geometri: sudut torso & diam',   durationSec: 3  },
  { label: 'Merender video beranotasi (kerangka sendi)',durationSec: 10 },
]
const TOTAL_EST = STEPS.reduce((s, st) => s + st.durationSec, 0)

export default function ProcessingPage({ onCancel, fileSizeMB = 0 }) {
  const [activeStep, setActiveStep] = useState(0)
  const [elapsed, setElapsed]       = useState(0)

  const estimateSec = Math.max(30, Math.round(TOTAL_EST * Math.max(1, fileSizeMB / 30)))

  useEffect(() => {
    const t = setInterval(() => setElapsed(e => e + 1), 1000)
    return () => clearInterval(t)
  }, [])

  useEffect(() => {
    let acc = 0
    const timeouts = []
    STEPS.forEach((step, i) => {
      const delay = Math.round((acc / TOTAL_EST) * estimateSec * 1000)
      timeouts.push(setTimeout(() => setActiveStep(i), delay))
      acc += step.durationSec
    })
    return () => timeouts.forEach(clearTimeout)
  }, [estimateSec])

  const progress  = Math.min(elapsed / estimateSec, 0.97)
  const remaining = Math.max(0, estimateSec - elapsed)

  function fmt(sec) {
    if (sec < 60) return `${sec}d`
    return `${Math.floor(sec / 60)}m ${sec % 60}d`
  }

  return (
    <main className="page-center page-enter" style={{ maxWidth: 560, width: '100%', margin: '0 auto', gap: 0 }}>
      <div style={{ marginBottom: 32, position: 'relative', display: 'inline-block' }}>
        <WalkingSkeleton />
        <div style={{
          position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
          width: 168, height: 168, borderRadius: '50%',
          border: '1.5px solid rgba(47,107,88,0.14)',
          animation: 'spin 10s linear infinite', pointerEvents: 'none',
        }} />
        <div style={{
          position: 'absolute', top: '50%', left: '50%', transform: 'translate(-50%, -50%)',
          width: 210, height: 210, borderRadius: '50%',
          border: '1px solid rgba(47,107,88,0.07)',
          animation: 'spin 16s linear infinite reverse', pointerEvents: 'none',
        }} />
      </div>

      <h2 style={{
        fontFamily: "'DM Sans', sans-serif", fontSize: 24, fontWeight: 800,
        marginBottom: 8, color: 'var(--ink)', textAlign: 'center', letterSpacing: '-0.02em',
      }}>
        Sedang Menganalisis Video
      </h2>

      <div style={{
        display: 'flex', gap: 16, justifyContent: 'center', marginBottom: 20,
        fontFamily: "'JetBrains Mono', monospace", fontSize: 12, color: 'var(--ink-faint)',
      }}>
        <span>⏱ Berlangsung: <strong style={{ color: 'var(--ink-soft)' }}>{fmt(elapsed)}</strong></span>
        {remaining > 5 && (
          <span>≈ sisa <strong style={{ color: 'var(--ink-soft)' }}>{fmt(remaining)}</strong></span>
        )}
      </div>

      <div style={{
        width: '100%', height: 4, background: 'var(--garis)',
        borderRadius: 99, overflow: 'hidden', marginBottom: 28,
      }}>
        <div style={{
          height: '100%', borderRadius: 99, background: 'var(--sigap)',
          width: `${Math.round(progress * 100)}%`,
          transition: 'width 1s ease',
        }} />
      </div>

      <div className="card" style={{ width: '100%', padding: '8px 20px', marginBottom: 28 }}>
        {STEPS.map((step, i) => {
          const done    = i < activeStep
          const current = i === activeStep
          return (
            <div key={i} className="process-step">
              <div style={{
                width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                background: done ? 'var(--sigap)' : current ? 'var(--sigap-soft)' : 'transparent',
                border: done || current ? 'none' : '1.5px solid var(--garis)',
                color: done ? '#fff' : 'var(--sigap-dark)',
                fontSize: 11, fontWeight: 700,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontFamily: "'JetBrains Mono', monospace",
                transition: 'background 0.4s',
              }}>
                {done ? '✓' : String(i + 1).padStart(2, '0')}
              </div>
              <span style={{
                fontSize: 13, lineHeight: 1.5,
                color: done ? 'var(--ink)' : current ? 'var(--ink-soft)' : 'var(--ink-faint)',
                fontWeight: current ? 600 : 400,
                transition: 'color 0.4s',
              }}>
                {step.label}
              </span>
              {current && <div className="process-step-dot" style={{ animation: 'pulse 1.4s ease-in-out infinite' }} />}
              {done    && <div style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--sigap)', flexShrink: 0 }} />}
            </div>
          )
        })}
      </div>

      <button id="cancel-analysis-btn" type="button" className="btn btn-ghost" onClick={onCancel} style={{ fontSize: 14 }}>
        Batalkan
      </button>
    </main>
  )
}
