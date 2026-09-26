import { useState, useRef, useEffect, useCallback, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import JamLangsung from '../components/JamLangsung.jsx'
import KartuKejadian from '../components/KartuKejadian.jsx'
import { dedupeEvents, eventId } from '../utils/dedupeEvents.js'

/* ─────────────────────────────────────────────────────────────────────────────
   LivePage — Mode Live Demo (WebSocket webcam)
   Konek ke /api/ws/live → nginx proxy → backend:8000/ws/live
───────────────────────────────────────────────────────────────────────────── */

const COCO_SKELETON = [
  [0,1],[0,2],[1,3],[2,4],          // wajah
  [5,6],                             // bahu
  [5,7],[7,9],[6,8],[8,10],         // lengan
  [5,11],[6,12],[11,12],            // torso
  [11,13],[13,15],[12,14],[14,16],  // kaki
]

// Warna sama dengan render.py (tapi dalam format CSS)
const C_NORMAL = 'rgba(80,180,80,0.9)'    // hijau — gerakan normal
const C_FALL   = 'rgba(210,40,40,0.95)'   // merah — jatuh
const C_HELP   = 'rgba(240,140,30,0.95)'  // oranye — butuh bantuan
const C_EMPLOYEE = 'rgba(35,125,220,0.95)' // biru — pegawai terdaftar

function buildWsUrl() {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${proto}//${window.location.host}/api/ws/live`
}

function trackColor(trackId, activeEvents, employeeIds) {
  const evs = activeEvents.filter(e => e.track_id === trackId)
  if (evs.some(e => e.tipe === 'jatuh'))         return C_FALL
  if (employeeIds.has(trackId))                    return C_EMPLOYEE
  if (evs.some(e => e.tipe === 'butuh_bantuan')) return C_HELP
  return C_NORMAL
}

function drawSkeleton(ctx, keypoints, color) {
  ctx.strokeStyle = color
  ctx.fillStyle   = color
  ctx.lineWidth   = 2.5

  for (const [j1, j2] of COCO_SKELETON) {
    const [x1,y1,c1] = keypoints[j1]
    const [x2,y2,c2] = keypoints[j2]
    if (c1 > 0.25 && c2 > 0.25) {
      ctx.beginPath()
      ctx.moveTo(x1, y1)
      ctx.lineTo(x2, y2)
      ctx.stroke()
    }
  }
  for (const [x, y, c] of keypoints) {
    if (c > 0.25) {
      ctx.beginPath()
      ctx.arc(x, y, 5, 0, Math.PI * 2)
      ctx.fill()
    }
  }
}

function drawLabel(ctx, text, x, y, color) {
  ctx.font = 'bold 13px "DM Sans", sans-serif'
  const m   = ctx.measureText(text)
  const pad = 5
  const bx  = x - pad
  const by  = y - 16
  const bw  = m.width + pad * 2
  const bh  = 20

  ctx.fillStyle = 'rgba(0,0,0,0.75)'
  ctx.beginPath()
  ctx.roundRect(bx, by, bw, bh, 4)
  ctx.fill()

  ctx.strokeStyle = color
  ctx.lineWidth   = 1
  ctx.stroke()

  ctx.fillStyle = '#ffffff'
  ctx.fillText(text, x, y)
}

export default function LivePage() {
  const navigate = useNavigate()

  const videoRef     = useRef(null)
  const canvasRef    = useRef(null)
  const wsRef        = useRef(null)
  const timerRef     = useRef(null)
  const rafRef       = useRef(null)
  const startTimeRef = useRef(null)
  const poseRef      = useRef({})    // mutable ref — tidak trigger re-render
  const employeeRef  = useRef(new Set())
  const eventsRef    = useRef([])
  const isRunningRef  = useRef(false) // dibaca timer 'terlewat' tanpa jadi dependency

  const [cameraType, setCameraType] = useState('lorong')
  const [wsState, setWsState]       = useState('idle')
  const [events,  setEvents]        = useState([])
  const [errorMsg, setErrorMsg]     = useState('')
  // Status penanganan per eventId. Nilai:
  //   { status: 'ditangani'|'palsu'|'terlewat', tRespons?: detik }
  // tRespons = selisih waktu dari kejadian muncul sampai pengawas menekan tombol.
  const [statusMap, setStatusMap]   = useState({})
  // Waktu (ms epoch) saat tiap eventId pertama muncul — untuk hitung waktu respons.
  const munculRef = useRef({})        // eventId → ms epoch
  const [, paksaRender] = useState(0) // untuk memicu re-render saat timeout jalan

  // Batas waktu respons: bila lewat ini tanpa aksi, kejadian ditandai "terlewat".
  const BATAS_RESPONS_MS = 60_000     // 1 menit

  // Dedup event Live (spam per ~1 dtk → satu kartu), lalu balik agar terbaru di atas.
  const kejadianTampil = useMemo(() => {
    const merged = dedupeEvents(events)   // urut menaik by t0
    return merged.reverse()               // terbaru di atas
  }, [events])

  // Catat kemunculan pertama tiap kejadian (untuk waktu respons + timeout).
  useEffect(() => {
    const now = Date.now()
    for (const ev of kejadianTampil) {
      const id = eventId(ev)
      if (!(id in munculRef.current)) munculRef.current[id] = now
    }
  }, [kejadianTampil])

  // Timer: tandai kejadian yang belum direspons > 1 menit sebagai "terlewat".
  useEffect(() => {
    if (!isRunningRef.current) return
    const timer = setInterval(() => {
      const now = Date.now()
      let berubah = false
      setStatusMap(m => {
        const next = { ...m }
        for (const [id, tMuncul] of Object.entries(munculRef.current)) {
          if (!next[id] && now - tMuncul > BATAS_RESPONS_MS) {
            next[id] = { status: 'terlewat' }
            berubah = true
          }
        }
        return berubah ? next : m
      })
      paksaRender(n => n + 1)  // perbarui label "x dtk lalu" bila ada
    }, 5000)
    return () => clearInterval(timer)
  }, [])

  // Polling statistik backend: tarik status "ditangani" dari Telegram (staf
  // lapangan) supaya panel Live ikut menampilkannya. Satu arah & ringan —
  // tidak menyentuh WebSocket. Status lokal (mis. "palsu" dari pengawas) tidak
  // ditimpa; hanya kejadian yang belum final di UI yang diperbarui.
  useEffect(() => {
    let batal = false
    async function tarik() {
      if (!isRunningRef.current) return
      try {
        const res = await fetch('/api/statistik')
        if (!res.ok || batal) return
        const data = await res.json()
        const dariBackend = {}
        for (const r of data.riwayat || []) {
          if (r.status === 'ditangani') {
            dariBackend[r.id] = { status: 'ditangani', tRespons: r.respons_detik, oleh: r.oleh, sumber: 'telegram' }
          }
        }
        if (Object.keys(dariBackend).length === 0) return
        setStatusMap(m => {
          let berubah = false
          const next = { ...m }
          for (const [id, st] of Object.entries(dariBackend)) {
            // Jangan timpa status final yang sudah ada di UI (mis. alarm palsu).
            const skrg = next[id]?.status
            if (skrg === 'ditangani' || skrg === 'palsu') continue
            next[id] = st
            berubah = true
          }
          return berubah ? next : m
        })
      } catch { /* diabaikan — polling berikutnya coba lagi */ }
    }
    const id = setInterval(tarik, 5000)
    return () => { batal = true; clearInterval(id) }
  }, [])

  // Ringkasan + statistik sesi real-time (metrik TIM, bukan individu).
  const statistik = useMemo(() => {
    let jatuh = 0, bantu = 0, ditangani = 0, palsu = 0, terlewat = 0
    let totalRespons = 0, nRespons = 0
    for (const ev of kejadianTampil) {
      const st = statusMap[eventId(ev)]
      const s = st?.status
      if (s === 'palsu') { palsu++; continue }
      if (s === 'terlewat') { terlewat++; continue }
      if (s === 'ditangani') {
        ditangani++
        if (st.tRespons != null) { totalRespons += st.tRespons; nRespons++ }
        continue
      }
      // belum direspons → hitung sebagai "sedang berlangsung"
      if (ev.tipe === 'jatuh') jatuh++
      else bantu++
    }
    const avgRespons = nRespons > 0 ? totalRespons / nRespons : null
    return {
      total: kejadianTampil.length,
      jatuh, bantu, ditangani, palsu, terlewat, avgRespons,
    }
  }, [kejadianTampil, statusMap])

  // Kirim sinyal batalkan ke backend (hapus notif Telegram) — dipakai saat palsu.
  const kirimBatalkan = useCallback((ev) => {
    const ws = wsRef.current
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({
        type: 'batalkan',
        track_id: ev.track_id,
        tipe: ev.tipe,
        t0: ev.t0,
      }))
    }
  }, [])

  const tandaiStatus = useCallback((id, status, ev) => {
    const tMuncul = munculRef.current[id]
    const tRespons = tMuncul ? (Date.now() - tMuncul) / 1000 : null
    setStatusMap(m => ({ ...m, [id]: { status, tRespons } }))
    // Alarm palsu → minta backend hapus notifikasi Telegram terkait.
    if (status === 'palsu' && ev) kirimBatalkan(ev)
  }, [kirimBatalkan])

  const batalkanStatus = useCallback((id) => {
    setStatusMap(m => {
      const next = { ...m }
      delete next[id]
      return next
    })
  }, [])

  const getT = () => startTimeRef.current ? (Date.now() - startTimeRef.current) / 1000 : 0

  /* RAF loop — gambar skeleton terus-menerus */
  function startRafLoop() {
    function loop() {
      const canvas = canvasRef.current
      const video  = videoRef.current
      if (!canvas || !video || video.videoWidth === 0) {
        rafRef.current = requestAnimationFrame(loop)
        return
      }

      // Sinkronkan ukuran canvas dengan video
      if (canvas.width !== video.videoWidth)  canvas.width  = video.videoWidth
      if (canvas.height !== video.videoHeight) canvas.height = video.videoHeight

      const ctx = canvas.getContext('2d')
      ctx.clearRect(0, 0, canvas.width, canvas.height)

      const t = getT()
      const active = eventsRef.current.filter(e => e.t0 <= t && t <= (e.t1 ?? t + 5))

      for (const [trackId, kps] of Object.entries(poseRef.current)) {
        const tid = Number(trackId)
        const col = trackColor(tid, active, employeeRef.current)
        drawSkeleton(ctx, kps, col)

        // Label di atas kepala / bahu
        const [nx, ny, nc] = kps[0]
        const cx = nc > 0.25 ? nx : (kps[5][0] + kps[6][0]) / 2
        const cy = nc > 0.25 ? ny : (kps[5][1] + kps[6][1]) / 2

        const hasFall = active.some(e => e.track_id === tid && e.tipe === 'jatuh')
        const hasHelp = active.some(e => e.track_id === tid && e.tipe === 'butuh_bantuan')
        const isEmployee = employeeRef.current.has(tid)
        const statusTxt = hasFall ? 'JATUH!' : isEmployee ? 'PEGAWAI' : hasHelp ? 'BUTUH BANTUAN' : 'Normal'
        drawLabel(ctx, `ID:${tid}  ${statusTxt}`, cx - 30, cy - 12, col)
      }

      rafRef.current = requestAnimationFrame(loop)
    }
    rafRef.current = requestAnimationFrame(loop)
  }

  function stopRafLoop() {
    if (rafRef.current) { cancelAnimationFrame(rafRef.current); rafRef.current = null }
  }

  /* Mulai live */
  const startLive = useCallback(async () => {
    setErrorMsg('')
    setWsState('connecting')
    setEvents([])
    setStatusMap({})
    munculRef.current = {}
    poseRef.current  = {}
    employeeRef.current = new Set()
    eventsRef.current = []

    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, facingMode: 'environment' },
        audio: false,
      })
    } catch {
      setErrorMsg('Tidak bisa mengakses kamera. Pastikan izin kamera sudah diberikan.')
      setWsState('error')
      return
    }

    const video = videoRef.current
    video.srcObject = stream
    await new Promise(res => { video.onloadedmetadata = res })
    video.play()

    // Mulai RAF loop langsung setelah video ready
    startRafLoop()

    const ws = new WebSocket(buildWsUrl())
    wsRef.current    = ws
    startTimeRef.current = Date.now()

    ws.onopen = () => {
      setWsState('connected')

      const offscreen = document.createElement('canvas')
      const octx = offscreen.getContext('2d')

      timerRef.current = setInterval(() => {
        if (ws.readyState !== WebSocket.OPEN) return
        const v = videoRef.current
        if (!v || v.videoWidth === 0) return

        offscreen.width  = v.videoWidth
        offscreen.height = v.videoHeight
        octx.drawImage(v, 0, 0)
        const image = offscreen.toDataURL('image/jpeg', 0.65)

        ws.send(JSON.stringify({ type: 'frame', image, t: getT(), camera_type: cameraType }))
      }, 200)
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'pose') {
          poseRef.current = msg.tracks ?? {}  // update langsung, RAF loop ambil sendiri
          employeeRef.current = new Set((msg.pegawai ?? []).map(Number))
        } else if (msg.type === 'event') {
          eventsRef.current = [msg, ...eventsRef.current].slice(0, 50)
          setEvents(ev => [msg, ...ev].slice(0, 50))  // update UI
        } else if (msg.type === 'error') {
          setErrorMsg(msg.detail ?? 'Error dari server.')
        }
      } catch {}
    }

    ws.onerror = () => {
      setErrorMsg('Koneksi WebSocket gagal. Pastikan backend berjalan.')
      setWsState('error')
      stopLive()
    }

    ws.onclose = () => {
      setWsState(st => st === 'connected' ? 'idle' : st)
    }
  }, [cameraType])

  /* Hentikan live */
  const stopLive = useCallback(() => {
    clearInterval(timerRef.current)
    timerRef.current = null
    stopRafLoop()

    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    const video = videoRef.current
    if (video?.srcObject) {
      video.srcObject.getTracks().forEach(t => t.stop())
      video.srcObject = null
    }

    poseRef.current   = {}
    employeeRef.current = new Set()
    eventsRef.current = []
    setWsState('idle')

    // Bersihkan canvas
    const canvas = canvasRef.current
    if (canvas) {
      const ctx = canvas.getContext('2d')
      ctx.clearRect(0, 0, canvas.width, canvas.height)
    }
  }, [])

  /* Bersihkan saat unmount */
  useEffect(() => () => stopLive(), [])

  const isRunning = wsState === 'connected'
  useEffect(() => { isRunningRef.current = isRunning }, [isRunning])
  const isLoading = wsState === 'connecting'

  function formatTime(sec) {
    const m = Math.floor(sec / 60)
    const s = Math.floor(sec % 60)
    return `${m}:${String(s).padStart(2,'0')}`
  }

  return (
    <div className="page-container" style={{ background: 'var(--paper)' }}>
      {/* ── Navbar ─────────────────────────────────────────────────── */}
      <nav className="navbar">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          {/* Tombol kembali eksplisit — hentikan live dulu agar kamera & WS bersih */}
          <button
            onClick={() => { stopLive(); navigate('/') }}
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

          <button
            className="navbar-brand"
            onClick={() => { stopLive(); navigate('/') }}
            style={{ cursor: 'pointer', background: 'none', border: 'none', padding: 0 }}
            aria-label="Kembali ke halaman utama"
          >
            <div className="navbar-logo">
              <img src="/sapa.png" alt="SAPA Logo" />
            </div>
            <div>
              <div className="navbar-title">SAPA</div>
            </div>
          </button>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          {/* Timestamp wajib untuk video proof of work — lihat JamLangsung.jsx */}
          <JamLangsung ringkas />
          <span style={{
            width: 8, height: 8, borderRadius: '50%',
            background: isRunning ? '#ef4444' : 'var(--ink-faint)',
            boxShadow: isRunning ? '0 0 8px #ef4444' : 'none',
            animation: isRunning ? 'pulse 1.2s ease-in-out infinite' : 'none',
            display: 'inline-block',
          }} />
          <span style={{ fontSize: 12, fontWeight: 700, color: isRunning ? '#ef4444' : 'var(--ink-faint)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            {isRunning ? 'LIVE' : 'Mode Live (Demo)'}
          </span>
          <div className="navbar-badge" style={{ marginLeft: 8 }}>Privacy-by-Design</div>
        </div>
      </nav>

      <main style={{ flex: 1, maxWidth: 1200, width: '100%', margin: '0 auto', padding: '32px 20px 60px' }}>
        <div style={{ marginBottom: 24, textAlign: 'center' }}>
          <h1 style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 'clamp(22px,4vw,36px)',
            fontWeight: 800, marginBottom: 10, color: 'var(--ink)', letterSpacing: '-0.03em',
          }}>
            Mode Kamera Real-time
          </h1>
          <p style={{ color: 'var(--ink-soft)', fontSize: 15, maxWidth: 480, margin: '0 auto', lineHeight: 1.6 }}>
            Deteksi real-time via WebSocket — hanya dari kerangka tubuh, tanpa mengenali wajah.
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 310px', gap: 24, alignItems: 'start' }}>
          {/* ── Video + Canvas overlay ──────────────────────────────── */}
          <div>
            <div style={{
              borderRadius: 'var(--radius-xl)', overflow: 'hidden',
              background: '#111', border: '1px solid var(--garis)',
              boxShadow: 'var(--shadow-md)', position: 'relative',
              aspectRatio: '16/9',
            }}>
              <video
                ref={videoRef}
                muted playsInline
                style={{ width: '100%', height: '100%', objectFit: 'cover', display: 'block' }}
              />
              <canvas
                ref={canvasRef}
                style={{
                  position: 'absolute', top: 0, left: 0,
                  width: '100%', height: '100%', pointerEvents: 'none',
                }}
              />

              {/* Placeholder */}
              {!isRunning && !isLoading && (
                <div style={{
                  position: 'absolute', inset: 0,
                  display: 'flex', flexDirection: 'column',
                  alignItems: 'center', justifyContent: 'center',
                  background: 'rgba(245,243,234,0.93)', gap: 14,
                }}>
                  <svg width="56" height="56" viewBox="0 0 56 56" fill="none">
                    <circle cx="28" cy="28" r="24" stroke="var(--garis)" strokeWidth="1.5" fill="var(--paper-2)" />
                    <circle cx="28" cy="18" r="6" stroke="var(--ink-faint)" strokeWidth="1.8" />
                    <path d="M16 40c0-6.6 5.4-12 12-12s12 5.4 12 12" stroke="var(--ink-faint)" strokeWidth="1.8" strokeLinecap="round" />
                  </svg>
                  <span style={{ fontSize: 14, color: 'var(--ink-soft)', fontWeight: 500 }}>
                    Klik "Mulai Live" untuk mengaktifkan kamera
                  </span>
                </div>
              )}
              {isLoading && (
                <div style={{
                  position: 'absolute', inset: 0,
                  display: 'flex', flexDirection: 'column',
                  alignItems: 'center', justifyContent: 'center',
                  background: 'rgba(245,243,234,0.93)', gap: 12,
                }}>
                  <div className="progress-track" style={{ width: 160 }}>
                    <div className="progress-sweep" />
                  </div>
                  <span style={{ fontSize: 13, color: 'var(--ink-soft)' }}>Menghubungkan…</span>
                </div>
              )}
            </div>

            {/* Legenda warna */}
            <div style={{
              marginTop: 10, display: 'flex', gap: 16, flexWrap: 'wrap',
              fontSize: 12, color: 'var(--ink-soft)',
            }}>
              {[
                { color: C_NORMAL, label: 'Hijau = Gerakan normal' },
                { color: C_EMPLOYEE, label: 'Biru = Pegawai terdaftar' },
                { color: C_HELP,   label: 'Oranye = Butuh bantuan' },
                { color: C_FALL,   label: 'Merah = Jatuh terdeteksi' },
              ].map(({ color, label }) => (
                <span key={label} style={{ display: 'flex', alignItems: 'center', gap: 5 }}>
                  <span style={{ width: 12, height: 4, borderRadius: 99, background: color, display: 'inline-block' }} />
                  {label}
                </span>
              ))}
            </div>

            {/* Kontrol */}
            <div style={{ marginTop: 14, display: 'flex', gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', gap: 6 }}>
                {[{ id:'lorong', label:'Lorong (Samping)' }, { id:'rak', label:'Rak (Atas)' }, { id:'both', label:'Semua Fitur' }].map(opt => (
                  <button
                    key={opt.id} type="button"
                    onClick={() => setCameraType(opt.id)}
                    disabled={isRunning || isLoading}
                    style={{
                      padding: '6px 14px', borderRadius: 20, fontSize: 13, fontWeight: 600,
                      fontFamily: 'inherit', cursor: isRunning || isLoading ? 'not-allowed' : 'pointer',
                      border: `1.5px solid ${cameraType === opt.id ? 'var(--sigap)' : 'var(--garis)'}`,
                      background: cameraType === opt.id ? 'var(--sigap-soft)' : 'var(--surface)',
                      color: cameraType === opt.id ? 'var(--sigap-dark)' : 'var(--ink-soft)',
                      transition: 'all 0.2s', opacity: isRunning ? 0.5 : 1,
                    }}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

              {!isRunning ? (
                <button
                  id="start-live-btn" type="button"
                  className="btn btn-primary"
                  onClick={startLive} disabled={isLoading}
                  style={{ fontSize: 14, padding: '8px 22px' }}
                >
                  {isLoading ? 'Menghubungkan…' : '▶ Mulai Live'}
                </button>
              ) : (
                <button
                  id="stop-live-btn" type="button"
                  className="btn btn-ghost"
                  onClick={stopLive}
                  style={{ fontSize: 14, padding: '8px 22px' }}
                >
                  ■ Hentikan
                </button>
              )}

              {errorMsg && (
                <span style={{ fontSize: 13, color: 'var(--waspada-dark)', fontWeight: 500 }}>
                  ⚠ {errorMsg}
                </span>
              )}
            </div>

            <div className="privacy-note" style={{ marginTop: 10 }}>
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
                <path d="M6.5 1L1.5 3v3.5c0 3 2.2 5.8 5 6.5 2.8-.7 5-3.5 5-6.5V3L6.5 1z"
                  stroke="var(--ink-faint)" strokeWidth="1.3" fill="none" strokeLinejoin="round" />
              </svg>
              Video diproses di server lokal — deteksi memakai kerangka tubuh, bukan wajah
            </div>
          </div>

          {/* ── Log kejadian live ────────────────────────────────────── */}
          <div>
            <div style={{
              display: 'flex', justifyContent: 'space-between', alignItems: 'baseline',
              marginBottom: 10,
            }}>
              <div style={{
                fontSize: 12, fontWeight: 700, color: 'var(--ink-soft)',
                letterSpacing: '0.07em', textTransform: 'uppercase',
              }}>
                Kejadian Live
              </div>
              {kejadianTampil.length > 0 && (
                <span style={{ fontFamily: "'JetBrains Mono', monospace", fontSize: 11, color: 'var(--ink-faint)' }}>
                  {kejadianTampil.length} kejadian
                </span>
              )}
            </div>

            {/* Statistik sesi real-time (metrik TIM, bukan individu) */}
            {kejadianTampil.length > 0 && (
              <div style={{ marginBottom: 10 }}>
                <div style={{
                  padding: '10px 14px',
                  borderRadius: 'var(--radius-md)',
                  background: 'var(--paper-2)', border: '1px solid var(--garis)',
                  fontSize: 12, color: 'var(--ink-soft)', lineHeight: 1.5, marginBottom: 8,
                }}>
                  Sedang berlangsung:{' '}
                  <strong style={{ color: 'var(--waspada)' }}>{statistik.jatuh} jatuh</strong>,{' '}
                  <strong style={{ color: 'var(--bantu)' }}>{statistik.bantu} butuh bantuan</strong>
                </div>

                {/* Grid metrik ringkas */}
                <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 6 }}>
                  {[
                    { label: 'Ditangani', nilai: statistik.ditangani, warna: 'var(--sigap)' },
                    { label: 'Alarm palsu', nilai: statistik.palsu, warna: 'var(--ink-faint)' },
                    { label: 'Terlewat', nilai: statistik.terlewat, warna: 'var(--waspada)' },
                  ].map(s => (
                    <div key={s.label} style={{
                      padding: '8px 10px', borderRadius: 'var(--radius-sm)',
                      background: 'var(--surface)', border: '1px solid var(--garis)',
                      textAlign: 'center',
                    }}>
                      <div style={{ fontSize: 20, fontWeight: 800, color: s.warna, lineHeight: 1 }}>
                        {s.nilai}
                      </div>
                      <div style={{ fontSize: 10, color: 'var(--ink-faint)', marginTop: 3, letterSpacing: '0.03em' }}>
                        {s.label}
                      </div>
                    </div>
                  ))}
                </div>

                {/* Waktu respons rata-rata */}
                <div style={{
                  marginTop: 6, padding: '8px 12px', borderRadius: 'var(--radius-sm)',
                  background: 'var(--sigap-soft)', border: '1px solid rgba(47,107,88,0.18)',
                  fontSize: 12, color: 'var(--ink-soft)', display: 'flex', justifyContent: 'space-between',
                }}>
                  <span>Rata-rata waktu respons</span>
                  <strong style={{ color: 'var(--sigap-dark)', fontFamily: "'JetBrains Mono', monospace" }}>
                    {statistik.avgRespons != null ? `${statistik.avgRespons.toFixed(1)} dtk` : '—'}
                  </strong>
                </div>

                <div style={{ fontSize: 10.5, color: 'var(--ink-faint)', marginTop: 6, lineHeight: 1.5 }}>
                  Metrik mengukur respons <strong>tim</strong> toko, bukan individu —
                  sejalan dengan prinsip privacy-by-design.
                </div>
              </div>
            )}

            <div style={{
              display: 'flex', flexDirection: 'column', gap: 8,
              maxHeight: 440, overflowY: 'auto', paddingRight: 2,
            }}>
              {kejadianTampil.length === 0 ? (
                <div style={{
                  background: 'var(--surface)', border: '1px solid var(--garis)',
                  borderRadius: 'var(--radius-lg)',
                  padding: '36px 24px', textAlign: 'center', color: 'var(--ink-faint)', fontSize: 13,
                }}>
                  {isRunning ? (
                    <span>🔍 Memantau...<br/><span style={{ fontSize: 11, marginTop: 4, display: 'block' }}>kerangka akan muncul di kamera saat terdeteksi</span></span>
                  ) : 'Belum ada kejadian'}
                </div>
              ) : kejadianTampil.map((ev) => {
                const id = eventId(ev)
                return (
                  <KartuKejadian
                    key={id}
                    event={ev}
                    mode="live"
                    status={statusMap[id]?.status}
                    tRespons={statusMap[id]?.tRespons}
                    oleh={statusMap[id]?.oleh}
                    sumber={statusMap[id]?.sumber}
                    onAck={(x) => tandaiStatus(x, 'ditangani', ev)}
                    onPalsu={(x) => tandaiStatus(x, 'palsu', ev)}
                    onUndo={batalkanStatus}
                  />
                )
              })}
            </div>

            <div className="info-box" style={{ marginTop: 10, fontSize: 12 }}>
              Overlay kerangka sendi langsung digambar di atas video — wajah tidak dikenali.
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
