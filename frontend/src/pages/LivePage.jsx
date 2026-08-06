import { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'

/* ─────────────────────────────────────────────────────────────────────────────
   LivePage — Mode Live Demo (WebSocket webcam)
   Label eksplisit "Mode Live (Demo)" — bukan bagian dari alur submission inti.

   Protokol WS (sesuai addendum B.2):
   Browser → Server: { type:"frame", image:"data:image/jpeg;base64,...", t, camera_type }
   Server → Browser: { type:"pose",  t, tracks:{id:[[x,y,conf]×17]}} 
                     { type:"event", tipe:"jatuh"|"butuh_bantuan", t0, t1, track_id }

   COCO-17 skeleton edges untuk overlay canvas
───────────────────────────────────────────────────────────────────────────── */

const COCO_SKELETON = [
  [0,1],[0,2],[1,3],[2,4],                 // wajah
  [5,6],                                    // bahu
  [5,7],[7,9],[6,8],[8,10],                // lengan
  [5,11],[6,12],[11,12],                   // torso
  [11,13],[13,15],[12,14],[14,16],         // kaki
]

const WS_URL = import.meta.env.VITE_WS_URL
  ? `${import.meta.env.VITE_WS_URL}/ws/live`
  : '/ws/live'  // dev: proxied oleh vite, prod: langsung ke backend

const FRAME_INTERVAL_MS = 200  // kirim 5 fps ke server

/* Gambar skeleton di canvas */
function drawSkeleton(ctx, keypoints, color, scale = 1) {
  ctx.strokeStyle = color
  ctx.fillStyle   = color
  ctx.lineWidth   = 2

  // Gambar garis tulang
  for (const [j1, j2] of COCO_SKELETON) {
    const [x1,y1,c1] = keypoints[j1]
    const [x2,y2,c2] = keypoints[j2]
    if (c1 > 0.3 && c2 > 0.3) {
      ctx.beginPath()
      ctx.moveTo(x1 * scale, y1 * scale)
      ctx.lineTo(x2 * scale, y2 * scale)
      ctx.stroke()
    }
  }

  // Gambar titik sendi
  for (const [x, y, c] of keypoints) {
    if (c > 0.3) {
      ctx.beginPath()
      ctx.arc(x * scale, y * scale, 4, 0, Math.PI * 2)
      ctx.fill()
    }
  }
}

/* Pilih warna overlay berdasarkan event aktif track */
function trackColor(trackId, activeEvents) {
  const events = activeEvents.filter(e => e.track_id === trackId)
  if (events.some(e => e.tipe === 'jatuh'))         return 'rgba(193,69,59,0.9)'
  if (events.some(e => e.tipe === 'butuh_bantuan')) return 'rgba(222,159,60,0.9)'
  return 'rgba(47,107,88,0.85)'
}

export default function LivePage() {
  const navigate = useNavigate()

  const videoRef  = useRef(null)   // webcam stream
  const canvasRef = useRef(null)   // overlay canvas
  const wsRef     = useRef(null)
  const timerRef  = useRef(null)
  const startTimeRef = useRef(null)

  const [cameraType, setCameraType] = useState('lorong')
  const [wsState, setWsState] = useState('idle')  // idle | connecting | connected | error
  const [events, setEvents]   = useState([])       // log kejadian live
  const [poseData, setPoseData] = useState({})     // {trackId: [[x,y,c]×17]}
  const [errorMsg, setErrorMsg] = useState('')

  /* Hitung waktu relatif */
  const getT = () => startTimeRef.current
    ? (Date.now() - startTimeRef.current) / 1000
    : 0

  /* Gambar overlay setiap kali pose berubah */
  useEffect(() => {
    const canvas = canvasRef.current
    const video  = videoRef.current
    if (!canvas || !video || !video.videoWidth) return

    const ctx = canvas.getContext('2d')
    const W = canvas.width  = video.videoWidth
    const H = canvas.height = video.videoHeight
    ctx.clearRect(0, 0, W, H)

    // Tentukan event aktif di waktu sekarang
    const t = getT()
    const activeEvents = events.filter(e => e.t0 <= t && t <= (e.t1 ?? t + 5))

    for (const [trackId, keypoints] of Object.entries(poseData)) {
      const color = trackColor(Number(trackId), activeEvents)
      drawSkeleton(ctx, keypoints, color)
    }
  }, [poseData, events])

  /* Buka koneksi WebSocket + mulai kirim frame */
  const startLive = useCallback(async () => {
    setErrorMsg('')
    setWsState('connecting')
    setEvents([])
    setPoseData({})

    // 1. Minta akses kamera
    let stream
    try {
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: 'environment' }, audio: false })
    } catch {
      setErrorMsg('Tidak bisa mengakses kamera. Pastikan izin kamera sudah diberikan.')
      setWsState('error')
      return
    }

    const video = videoRef.current
    video.srcObject = stream
    await new Promise(res => { video.onloadedmetadata = res })
    video.play()

    // 2. Buka WebSocket
    const ws = new WebSocket(WS_URL)
    wsRef.current = ws
    startTimeRef.current = Date.now()

    ws.onopen = () => {
      setWsState('connected')

      // 3. Kirim frame tiap FRAME_INTERVAL_MS
      const offscreen = document.createElement('canvas')
      const octx = offscreen.getContext('2d')

      timerRef.current = setInterval(() => {
        if (ws.readyState !== WebSocket.OPEN) return
        offscreen.width  = video.videoWidth
        offscreen.height = video.videoHeight
        octx.drawImage(video, 0, 0)
        const image = offscreen.toDataURL('image/jpeg', 0.7)

        ws.send(JSON.stringify({
          type: 'frame',
          image,
          t: getT(),
          camera_type: cameraType,
        }))
      }, FRAME_INTERVAL_MS)
    }

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data)
        if (msg.type === 'pose') {
          setPoseData(msg.tracks ?? {})
        } else if (msg.type === 'event') {
          setEvents(prev => [msg, ...prev].slice(0, 50))  // simpan 50 event terakhir
        }
      } catch {}
    }

    ws.onerror = () => {
      setErrorMsg('Koneksi WebSocket gagal. Pastikan backend berjalan.')
      setWsState('error')
      stopLive()
    }

    ws.onclose = () => {
      if (wsState !== 'idle') setWsState('idle')
    }
  }, [cameraType])

  /* Hentikan live */
  const stopLive = useCallback(() => {
    clearInterval(timerRef.current)
    timerRef.current = null

    if (wsRef.current) {
      wsRef.current.close()
      wsRef.current = null
    }

    const video = videoRef.current
    if (video?.srcObject) {
      video.srcObject.getTracks().forEach(t => t.stop())
      video.srcObject = null
    }

    setWsState('idle')
    setPoseData({})
  }, [])

  /* Bersihkan saat unmount */
  useEffect(() => () => stopLive(), [])

  const isRunning = wsState === 'connected'
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
        <button
          className="navbar-brand"
          onClick={() => { stopLive(); navigate('/') }}
          style={{ cursor: 'pointer', background: 'none', border: 'none', padding: 0 }}
          aria-label="Kembali ke halaman utama"
        >
          <div className="navbar-logo">
            <svg width="20" height="26" viewBox="0 0 20 26" fill="none" aria-hidden="true">
              <circle cx="10" cy="3.5" r="2.5" stroke="white" strokeWidth="1.8" />
              <line x1="10" y1="6"  x2="10" y2="14" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
              <line x1="10" y1="9"  x2="4"  y2="13" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
              <line x1="10" y1="9"  x2="16" y2="13" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
              <line x1="10" y1="14" x2="7"  y2="22" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
              <line x1="10" y1="14" x2="13" y2="22" stroke="white" strokeWidth="1.8" strokeLinecap="round" />
            </svg>
          </div>
          <div>
            <div className="navbar-title">SAPA</div>
            <div className="navbar-subtitle">Melihat Kebutuhan, Bukan Wajah</div>
          </div>
        </button>
        {/* Label mode live eksplisit */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%',
            background: isRunning ? 'var(--waspada)' : 'var(--ink-faint)',
            boxShadow: isRunning ? '0 0 6px var(--waspada)' : 'none',
            animation: isRunning ? 'pulse 1.5s ease-in-out infinite' : 'none',
            display: 'inline-block',
          }} />
          <span style={{ fontSize: 12, fontWeight: 700, color: isRunning ? 'var(--waspada)' : 'var(--ink-faint)', letterSpacing: '0.06em', textTransform: 'uppercase' }}>
            Mode Live (Demo)
          </span>
          <div className="navbar-badge" style={{ marginLeft: 8 }}>Privacy-by-Design</div>
        </div>
      </nav>

      {/* ── Konten utama ───────────────────────────────────────────── */}
      <main style={{ flex: 1, maxWidth: 1200, width: '100%', margin: '0 auto', padding: '32px 20px 60px' }}>
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ fontSize: 24, fontWeight: 800, color: 'var(--ink)', letterSpacing: '-0.02em', marginBottom: 6 }}>
            Mode Live — Demo Webcam
          </h1>
          <p style={{ fontSize: 14, color: 'var(--ink-soft)', lineHeight: 1.6, maxWidth: 600 }}>
            Pipeline yang sama persis dengan analisis upload — hanya sumber video berbeda (webcam vs file).
            Ini adalah pratinjau visi produksi, <strong>bukan bagian dari submission inti yang dinilai juri</strong>.
          </p>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 320px', gap: 24, alignItems: 'start' }}>
          {/* ── Video + Canvas overlay ──────────────────────────────── */}
          <div>
            <div style={{
              borderRadius: 'var(--radius-xl)',
              overflow: 'hidden',
              background: '#1A1A1A',
              border: '1px solid var(--garis)',
              boxShadow: 'var(--shadow-md)',
              position: 'relative',
            }}>
              <video
                ref={videoRef}
                muted
                playsInline
                style={{ width: '100%', display: 'block', maxHeight: 480, objectFit: 'cover' }}
              />
              <canvas
                ref={canvasRef}
                style={{
                  position: 'absolute',
                  top: 0, left: 0,
                  width: '100%', height: '100%',
                  pointerEvents: 'none',
                }}
              />
              {/* Placeholder saat belum jalan */}
              {!isRunning && !isLoading && (
                <div style={{
                  position: 'absolute', inset: 0,
                  display: 'flex', flexDirection: 'column',
                  alignItems: 'center', justifyContent: 'center',
                  background: 'rgba(245,243,234,0.92)',
                  gap: 14,
                }}>
                  <svg width="56" height="56" viewBox="0 0 56 56" fill="none" aria-hidden="true">
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
                  background: 'rgba(245,243,234,0.92)',
                  gap: 12,
                }}>
                  <div className="progress-track" style={{ width: 160 }}>
                    <div className="progress-sweep" />
                  </div>
                  <span style={{ fontSize: 13, color: 'var(--ink-soft)' }}>Menghubungkan…</span>
                </div>
              )}
            </div>

            {/* Kontrol */}
            <div style={{ marginTop: 16, display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
              {/* Pilih kamera */}
              <div style={{ display: 'flex', gap: 8 }}>
                {[{ id:'lorong', label:'Lorong' }, { id:'rak', label:'Rak (Atas)' }].map(opt => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setCameraType(opt.id)}
                    disabled={isRunning || isLoading}
                    style={{
                      padding: '7px 16px',
                      borderRadius: 20,
                      fontSize: 13,
                      fontWeight: 600,
                      fontFamily: 'inherit',
                      cursor: isRunning || isLoading ? 'not-allowed' : 'pointer',
                      border: `1.5px solid ${cameraType === opt.id ? 'var(--sigap)' : 'var(--garis)'}`,
                      background: cameraType === opt.id ? 'var(--sigap-soft)' : 'var(--surface)',
                      color: cameraType === opt.id ? 'var(--sigap-dark)' : 'var(--ink-soft)',
                      transition: 'all var(--dur-fast) var(--ease)',
                      opacity: isRunning ? 0.5 : 1,
                    }}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

              {/* Tombol mulai/stop */}
              {!isRunning ? (
                <button
                  id="start-live-btn"
                  type="button"
                  className="btn btn-primary"
                  onClick={startLive}
                  disabled={isLoading}
                  style={{ fontSize: 14, padding: '10px 24px' }}
                >
                  {isLoading ? 'Menghubungkan…' : '▶ Mulai Live'}
                </button>
              ) : (
                <button
                  id="stop-live-btn"
                  type="button"
                  className="btn btn-ghost"
                  onClick={stopLive}
                  style={{ fontSize: 14, padding: '10px 24px' }}
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

            {/* Privacy note */}
            <div className="privacy-note" style={{ marginTop: 12 }}>
              <svg width="13" height="13" viewBox="0 0 13 13" fill="none" aria-hidden="true">
                <path d="M6.5 1L1.5 3v3.5c0 3 2.2 5.8 5 6.5 2.8-.7 5-3.5 5-6.5V3L6.5 1z"
                  stroke="var(--ink-faint)" strokeWidth="1.3" fill="none" strokeLinejoin="round" />
              </svg>
              Video hanya diproses di server lokal — tidak direkam atau disimpan
            </div>
          </div>

          {/* ── Log kejadian ────────────────────────────────────────── */}
          <div>
            <div style={{
              fontSize: 12, fontWeight: 700,
              color: 'var(--ink-soft)',
              letterSpacing: '0.07em',
              textTransform: 'uppercase',
              marginBottom: 12,
            }}>
              Kejadian Live
            </div>

            <div style={{
              background: 'var(--surface)',
              border: '1px solid var(--garis)',
              borderRadius: 'var(--radius-lg)',
              padding: '4px 0',
              maxHeight: 460,
              overflowY: 'auto',
            }}>
              {events.length === 0 ? (
                <div style={{
                  padding: '40px 24px',
                  textAlign: 'center',
                  color: 'var(--ink-faint)',
                  fontSize: 13,
                }}>
                  {isRunning ? 'Memantau…' : 'Belum ada kejadian'}
                </div>
              ) : events.map((ev, i) => {
                const isFall  = ev.tipe === 'jatuh'
                const color   = isFall ? 'var(--waspada)'   : 'var(--bantu)'
                const bgColor = isFall ? 'var(--waspada-soft)' : 'var(--bantu-soft)'
                const label   = isFall ? 'Jatuh Terdeteksi' : 'Tampak Butuh Bantuan'
                return (
                  <div key={i} style={{
                    padding: '12px 16px',
                    borderBottom: i < events.length - 1 ? '1px solid var(--garis-soft)' : 'none',
                    background: i === 0 ? bgColor : 'transparent',
                    transition: 'background 0.3s',
                  }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginBottom: 3 }}>
                      <span style={{ fontSize: 13, fontWeight: 700, color }}>{label}</span>
                      <span style={{
                        fontFamily: "'IBM Plex Mono', monospace",
                        fontSize: 10,
                        color: 'var(--ink-faint)',
                      }}>
                        {formatTime(ev.t0)}
                      </span>
                    </div>
                    <span style={{
                      fontFamily: "'IBM Plex Mono', monospace",
                      fontSize: 11,
                      color: 'var(--ink-faint)',
                    }}>
                      ID:{ev.track_id}
                    </span>
                  </div>
                )
              })}
            </div>

            {/* Info */}
            <div className="info-box" style={{ marginTop: 12, fontSize: 12 }}>
              Overlay kerangka sendi langsung digambar di atas video — wajah tidak dikenali.
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}
