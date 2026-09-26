import { useCallback, useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'

const MAX_FILES = 3

function UploadIcon() {
  return (
    <svg width="34" height="34" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path d="M12 16V4m0 0L7.5 8.5M12 4l4.5 4.5M5 14v4a2 2 0 002 2h10a2 2 0 002-2v-4"
        stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  )
}

export default function SeragamPage() {
  const navigate = useNavigate()
  const inputRef = useRef(null)
  const [nama, setNama] = useState('')
  const [files, setFiles] = useState([])
  const [pegawai, setPegawai] = useState([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState(null)
  const [dragging, setDragging] = useState(false)

  const loadPegawai = useCallback(async () => {
    try {
      const response = await fetch('/api/seragam')
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      const data = await response.json()
      setPegawai(data.pegawai || [])
    } catch {
      setMessage({ type: 'error', text: 'Daftar pegawai tidak dapat dimuat. Pastikan backend berjalan.' })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    window.scrollTo({ top: 0, left: 0, behavior: 'instant' })
    loadPegawai()
  }, [loadPegawai])

  function addFiles(selected) {
    const images = Array.from(selected).filter(file => file.type.startsWith('image/'))
    if (!images.length) {
      setMessage({ type: 'error', text: 'Pilih file gambar JPG, PNG, atau WEBP.' })
      return
    }
    setFiles(current => {
      const slots = Math.max(0, MAX_FILES - current.length)
      const added = images.slice(0, slots).map(file => ({ file, preview: URL.createObjectURL(file) }))
      if (images.length > slots) setMessage({ type: 'error', text: 'Maksimal 3 gambar untuk satu seragam.' })
      else setMessage(null)
      return [...current, ...added]
    })
  }

  function removeFile(index) {
    setFiles(current => {
      URL.revokeObjectURL(current[index].preview)
      return current.filter((_, i) => i !== index)
    })
  }

  async function submit(event) {
    event.preventDefault()
    if (!nama.trim() || files.length === 0) return
    setSaving(true)
    setMessage(null)
    const form = new FormData()
    form.append('nama', nama.trim())
    form.append('sudah_dicrop', 'true')
    files.forEach(item => form.append('files', item.file))
    try {
      const response = await fetch('/api/seragam/frame', { method: 'POST', body: form })
      const data = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(data.detail || `HTTP ${response.status}`)
      files.forEach(item => URL.revokeObjectURL(item.preview))
      setFiles([])
      setNama('')
      setMessage({ type: 'success', text: `Seragam “${data.nama}” berhasil didaftarkan dari ${data.n_sampel} gambar.` })
      await loadPegawai()
    } catch (error) {
      setMessage({ type: 'error', text: error.message || 'Registrasi seragam gagal.' })
    } finally {
      setSaving(false)
    }
  }

  async function removePegawai(item) {
    if (!window.confirm(`Hapus seragam “${item.nama}” dari daftar pegawai?`)) return
    try {
      const response = await fetch(`/api/seragam/${encodeURIComponent(item.id)}`, { method: 'DELETE' })
      if (!response.ok) throw new Error(`HTTP ${response.status}`)
      setMessage({ type: 'success', text: `Seragam “${item.nama}” berhasil dihapus.` })
      await loadPegawai()
    } catch {
      setMessage({ type: 'error', text: 'Seragam gagal dihapus. Coba lagi.' })
    }
  }

  return (
    <div className="page-container seragam-page">
      <nav className="navbar">
        <div className="seragam-nav-left">
          <button className="seragam-back" onClick={() => navigate('/')} aria-label="Kembali ke halaman utama">
            <span aria-hidden="true">‹</span> Home
          </button>
          <button className="navbar-brand" onClick={() => navigate('/')}>
            <div className="navbar-logo"><img src="/sapa.png" alt="SAPA Logo" /></div>
            <div><div className="navbar-title">SAPA</div><div className="navbar-subtitle">Kelola Seragam</div></div>
          </button>
        </div>
        <div className="navbar-badge">Tanpa wajah · Hanya ciri pakaian</div>
      </nav>

      <main className="seragam-main page-enter">
        <section className="seragam-heading">
          <div>
            <span className="chip chip-sigap">Identifikasi peran</span>
            <h1>Kenali pegawai dari seragam</h1>
            <p>Daftarkan potongan area torso seragam agar SAPA dapat membedakan pegawai dari pelanggan saat menganalisis video.</p>
          </div>
          <div className="seragam-privacy">
            <strong>Privacy-by-design</strong>
            <span>Gambar hanya diproses di memori. Sistem menyimpan sidik warna dan pola, bukan foto.</span>
          </div>
        </section>

        {message && <div className={`seragam-message ${message.type}`} role="status">{message.text}</div>}

        <div className="seragam-grid">
          <form className="card seragam-form" onSubmit={submit}>
            <div className="seragam-card-title"><span>01</span><div><h2>Daftarkan seragam</h2><p>Gunakan 1–3 gambar untuk hasil yang lebih stabil.</p></div></div>
            <label className="seragam-label" htmlFor="nama-pegawai">Nama atau label pegawai</label>
            <input id="nama-pegawai" className="seragam-input" value={nama} onChange={e => setNama(e.target.value)}
              placeholder="Contoh: Seragam kasir pagi" maxLength={80} />

            <input ref={inputRef} type="file" accept="image/jpeg,image/png,image/webp" multiple hidden
              onChange={e => { addFiles(e.target.files); e.target.value = '' }} />
            <button type="button" className={`seragam-dropzone ${dragging ? 'dragging' : ''}`}
              onClick={() => inputRef.current?.click()} disabled={files.length >= MAX_FILES}
              onDragOver={e => { e.preventDefault(); setDragging(true) }}
              onDragLeave={() => setDragging(false)}
              onDrop={e => { e.preventDefault(); setDragging(false); addFiles(e.dataTransfer.files) }}>
              <span className="seragam-upload-icon"><UploadIcon /></span>
              <strong>{files.length >= MAX_FILES ? 'Tiga gambar sudah dipilih' : 'Pilih atau tarik gambar ke sini'}</strong>
              <small>JPG, PNG, WEBP · maksimal 3 gambar</small>
            </button>

            <div className="seragam-tip"><strong>Area yang diperlukan</strong><span>Unggah gambar yang sudah dipotong dari bahu sampai pinggul. Hindari wajah, kaki, dan latar yang terlalu luas.</span></div>
            {files.length > 0 && <div className="seragam-previews">
              {files.map((item, index) => <div className="seragam-preview" key={`${item.file.name}-${index}`}>
                <img src={item.preview} alt={`Pratinjau ${index + 1}`} />
                <button type="button" onClick={() => removeFile(index)} aria-label={`Hapus ${item.file.name}`}>×</button>
                <span>{index + 1}</span>
              </div>)}
            </div>}

            <button className="btn btn-primary seragam-submit" disabled={saving || !nama.trim() || files.length === 0}>
              {saving ? 'Menyimpan…' : 'Daftarkan Seragam'}
            </button>
          </form>

          <section className="card seragam-list-card">
            <div className="seragam-card-title"><span>02</span><div><h2>Pegawai terdaftar</h2><p>{pegawai.length} profil seragam aktif.</p></div></div>
            {loading ? <div className="seragam-empty">Memuat daftar…</div> : pegawai.length === 0 ? (
              <div className="seragam-empty">
                <div className="seragam-empty-icon">◎</div>
                <strong>Belum ada seragam</strong>
                <p>Tambahkan seragam pertama melalui formulir di samping.</p>
              </div>
            ) : <div className="seragam-list">
              {pegawai.map((item, index) => <article key={item.id} className="seragam-person">
                <div className="seragam-avatar">{item.nama.trim().charAt(0).toUpperCase() || index + 1}</div>
                <div><strong>{item.nama}</strong><span>{item.n_sampel} sampel · ID {item.id}</span></div>
                <button type="button" onClick={() => removePegawai(item)}>Hapus</button>
              </article>)}
            </div>}
            <div className="seragam-behavior"><span>i</span><p>Pegawai dikecualikan dari sinyal <strong>butuh bantuan</strong> dan <strong>angkat tangan</strong>. Deteksi jatuh tetap aktif untuk semua orang.</p></div>
          </section>
        </div>
      </main>
    </div>
  )
}
