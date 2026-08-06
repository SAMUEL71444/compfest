import { useNavigate } from 'react-router-dom'

/* ─────────────────────────────────────────────────────────────────────────────
   LandingPage — redesign sesuai referensi visual
   Hero: 2 kolom (teks kiri, mockup UI kanan)
   Stats bar → Dua Fitur → Cara Kerja → Teaser Live → Privasi → CTA → Footer
───────────────────────────────────────────────────────────────────────────── */

/* ── Mockup produk (kanan hero) ─────────────────────────────────────────── */
function ProductMockup() {
  return (
    <div style={{
      width: '100%',
      maxWidth: 460,
      background: 'var(--surface)',
      border: '1px solid var(--garis)',
      borderRadius: 'var(--radius-xl)',
      boxShadow: 'var(--shadow-lg)',
      overflow: 'hidden',
      flexShrink: 0,
    }}>
      {/* Window chrome */}
      <div style={{
        padding: '12px 16px',
        background: 'var(--paper-2)',
        borderBottom: '1px solid var(--garis)',
        display: 'flex',
        alignItems: 'center',
        gap: 6,
      }}>
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#E5715A', display: 'inline-block' }} />
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#DEB94E', display: 'inline-block' }} />
        <span style={{ width: 10, height: 10, borderRadius: '50%', background: '#6CB96F', display: 'inline-block' }} />
      </div>

      {/* CCTV frame gelap */}
      <div style={{
        background: '#151510',
        padding: '18px 20px 14px',
        position: 'relative',
      }}>
        {/* Badge JATUH TERDETEKSI */}
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          background: 'var(--waspada)',
          color: 'white',
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: '0.07em',
          padding: '4px 10px',
          borderRadius: 6,
          marginBottom: 20,
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: 'rgba(255,255,255,0.8)',
            animation: 'pulse 1.5s ease-in-out infinite',
            display: 'inline-block',
          }} />
          JATUH TERDETEKSI
        </div>

        {/* Skeleton figure area */}
        <div style={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: 160,
          position: 'relative',
        }}>
          {/* Grid CCTV tipis */}
          <svg width="100%" height="160" style={{ position: 'absolute', inset: 0, opacity: 0.06 }}>
            <defs>
              <pattern id="grid" width="24" height="24" patternUnits="userSpaceOnUse">
                <path d="M 24 0 L 0 0 0 24" fill="none" stroke="white" strokeWidth="0.5" />
              </pattern>
            </defs>
            <rect width="100%" height="100%" fill="url(#grid)" />
          </svg>

          {/* Skeleton manusia berdiri (status jatuh — sedikit miring) */}
          <svg width="80" height="120" viewBox="0 0 80 120" fill="none" aria-hidden="true"
            style={{ animation: 'skeletonGlow 2.5s ease-in-out infinite' }}>
            {/* Kepala */}
            <circle cx="40" cy="14" r="10" stroke="#DE9F3C" strokeWidth="2.2" />
            {/* Badan */}
            <line x1="40" y1="24" x2="40" y2="58" stroke="#DE9F3C" strokeWidth="2.2" strokeLinecap="round" />
            {/* Lengan */}
            <line x1="40" y1="36" x2="18" y2="48" stroke="#DE9F3C" strokeWidth="2.2" strokeLinecap="round" />
            <line x1="40" y1="36" x2="62" y2="44" stroke="#DE9F3C" strokeWidth="2.2" strokeLinecap="round" />
            {/* Lengan bawah */}
            <line x1="18" y1="48" x2="10" y2="62" stroke="#DE9F3C" strokeWidth="2.2" strokeLinecap="round" />
            <line x1="62" y1="44" x2="70" y2="58" stroke="#DE9F3C" strokeWidth="2.2" strokeLinecap="round" />
            {/* Kaki */}
            <line x1="40" y1="58" x2="28" y2="86" stroke="#DE9F3C" strokeWidth="2.2" strokeLinecap="round" />
            <line x1="40" y1="58" x2="54" y2="84" stroke="#DE9F3C" strokeWidth="2.2" strokeLinecap="round" />
            <line x1="28" y1="86" x2="24" y2="106" stroke="#DE9F3C" strokeWidth="2.2" strokeLinecap="round" />
            <line x1="54" y1="84" x2="58" y2="104" stroke="#DE9F3C" strokeWidth="2.2" strokeLinecap="round" />
            {/* Titik sendi */}
            {[[40,24],[18,48],[62,44],[10,62],[70,58],[28,86],[54,84],[24,106],[58,104]].map(([cx,cy],i) => (
              <circle key={i} cx={cx} cy={cy} r="3.5" fill="#DE9F3C" opacity="0.9" />
            ))}
          </svg>

          {/* Badge 2 (normal) di kiri */}
          <svg width="52" height="80" viewBox="0 0 52 80" fill="none" aria-hidden="true"
            style={{ position: 'absolute', left: 12, opacity: 0.5 }}>
            <circle cx="26" cy="10" r="7" stroke="var(--sigap)" strokeWidth="1.8" />
            <line x1="26" y1="17" x2="26" y2="38" stroke="var(--sigap)" strokeWidth="1.8" strokeLinecap="round" />
            <line x1="26" y1="26" x2="14" y2="32" stroke="var(--sigap)" strokeWidth="1.8" strokeLinecap="round" />
            <line x1="26" y1="26" x2="38" y2="32" stroke="var(--sigap)" strokeWidth="1.8" strokeLinecap="round" />
            <line x1="26" y1="38" x2="20" y2="56" stroke="var(--sigap)" strokeWidth="1.8" strokeLinecap="round" />
            <line x1="26" y1="38" x2="32" y2="56" stroke="var(--sigap)" strokeWidth="1.8" strokeLinecap="round" />
          </svg>
        </div>
      </div>

      {/* Stats row */}
      <div style={{
        display: 'grid',
        gridTemplateColumns: '1fr 1fr 1fr',
        borderTop: '1px solid var(--garis)',
      }}>
        {[
          { val: '2',     label: 'butuh bantuan' },
          { val: '1',     label: 'deteksi jatuh' },
          { val: '02:14', label: 'durasi klip', mono: true },
        ].map((s, i) => (
          <div key={i} style={{
            padding: '14px 16px',
            borderRight: i < 2 ? '1px solid var(--garis)' : 'none',
          }}>
            <div style={{
              fontSize: 22,
              fontWeight: 700,
              fontFamily: s.mono ? "'IBM Plex Mono', monospace" : "'Fraunces', Georgia, serif",
              color: 'var(--ink)',
              letterSpacing: s.mono ? '0.02em' : '-0.02em',
              marginBottom: 2,
            }}>
              {s.val}
            </div>
            <div style={{ fontSize: 11, color: 'var(--ink-faint)', fontWeight: 500 }}>
              {s.label}
            </div>
          </div>
        ))}
      </div>

      {/* Badge wajah tidak dikenali */}
      <div style={{
        padding: '10px 18px 14px',
        display: 'flex',
        justifyContent: 'flex-end',
      }}>
        <div style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          background: 'var(--sigap-soft)',
          border: '1px solid rgba(47,107,88,0.2)',
          borderRadius: 20,
          padding: '5px 12px',
          fontSize: 11,
          fontWeight: 600,
          color: 'var(--sigap-dark)',
        }}>
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: 'var(--sigap)',
            display: 'inline-block',
          }} />
          Wajah tidak dikenali
        </div>
      </div>
    </div>
  )
}

/* ── Navbar ──────────────────────────────────────────────────────────────── */
function LandingNav({ onCTA, onLive }) {
  return (
    <nav style={{
      position: 'sticky', top: 0, zIndex: 100,
      padding: '0 40px', height: 60,
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      background: 'rgba(245,243,234,0.94)',
      backdropFilter: 'blur(16px)', WebkitBackdropFilter: 'blur(16px)',
      borderBottom: '1px solid var(--garis)',
    }}>
      {/* Brand */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
        <div style={{
          width: 32, height: 32, background: 'var(--sigap)',
          borderRadius: 9, display: 'flex', alignItems: 'center', justifyContent: 'center',
          boxShadow: '0 2px 8px rgba(47,107,88,0.28)',
        }}>
          <svg width="16" height="21" viewBox="0 0 16 21" fill="none" aria-hidden="true">
            <circle cx="8" cy="3" r="2.2" stroke="white" strokeWidth="1.6" />
            <line x1="8" y1="5.2"  x2="8"  y2="11" stroke="white" strokeWidth="1.6" strokeLinecap="round" />
            <line x1="8" y1="7.5"  x2="3"  y2="10" stroke="white" strokeWidth="1.6" strokeLinecap="round" />
            <line x1="8" y1="7.5"  x2="13" y2="10" stroke="white" strokeWidth="1.6" strokeLinecap="round" />
            <line x1="8" y1="11"   x2="5"  y2="17" stroke="white" strokeWidth="1.6" strokeLinecap="round" />
            <line x1="8" y1="11"   x2="11" y2="17" stroke="white" strokeWidth="1.6" strokeLinecap="round" />
          </svg>
        </div>
        <span style={{ fontFamily: "'Fraunces', Georgia, serif", fontSize: 20, fontWeight: 600, color: 'var(--ink)', letterSpacing: '-0.03em' }}>
          SAPA
        </span>
      </div>

      {/* Nav links */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {[
          { label: 'Cara Kerja', href: '#cara-kerja' },
          { label: 'Privasi',    href: '#privasi' },
        ].map(link => (
          <a key={link.label} href={link.href} style={{
            fontSize: 14, fontWeight: 500, color: 'var(--ink-soft)',
            textDecoration: 'none', padding: '5px 14px', borderRadius: 20,
            transition: 'color var(--dur-fast)',
          }}
          onMouseOver={e => e.target.style.color='var(--sigap)'}
          onMouseOut={e => e.target.style.color='var(--ink-soft)'}>
            {link.label}
          </a>
        ))}
        <button type="button" onClick={onLive}
          style={{
            fontSize: 14, fontWeight: 500, color: 'var(--ink-soft)',
            background: 'none', border: 'none', cursor: 'pointer',
            padding: '5px 14px', borderRadius: 20, fontFamily: 'inherit',
            display: 'flex', alignItems: 'center', gap: 5,
            transition: 'color var(--dur-fast)',
          }}
          onMouseOver={e => { e.currentTarget.style.color='var(--sigap)' }}
          onMouseOut={e => { e.currentTarget.style.color='var(--ink-soft)' }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--waspada)', display: 'inline-block', animation: 'pulse 1.5s ease-in-out infinite' }} />
          Mode Live
        </button>
        <button id="nav-cta-btn" type="button" onClick={onCTA} style={{
          marginLeft: 8,
          display: 'inline-flex', alignItems: 'center', gap: 6,
          background: 'var(--sigap)', color: 'white',
          fontSize: 14, fontWeight: 700, fontFamily: 'inherit',
          padding: '9px 22px', borderRadius: 50, border: 'none', cursor: 'pointer',
          boxShadow: '0 2px 12px rgba(47,107,88,0.28)',
          transition: 'all var(--dur-mid) var(--ease)',
          letterSpacing: '-0.01em',
        }}
        onMouseOver={e => { e.currentTarget.style.background='var(--sigap-dark)'; e.currentTarget.style.transform='translateY(-1px)' }}
        onMouseOut={e => { e.currentTarget.style.background='var(--sigap)'; e.currentTarget.style.transform='translateY(0)' }}>
          Mulai Analisis →
        </button>
      </div>
    </nav>
  )
}

/* ── Hero: dua kolom ─────────────────────────────────────────────────────── */
function HeroSection({ onCTA, onScrollHow }) {
  return (
    <section style={{
      padding: '80px 40px 72px',
      maxWidth: 1120, margin: '0 auto',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      gap: 56, flexWrap: 'wrap',
    }}>
      {/* Kiri — teks */}
      <div style={{ flex: '0 0 480px', maxWidth: 480 }}>
        {/* Eyebrow badge */}
        <div style={{
          display: 'inline-flex', alignItems: 'center', gap: 7,
          background: 'var(--sigap-soft)', border: '1px solid rgba(47,107,88,0.2)',
          borderRadius: 50, padding: '5px 14px',
          fontSize: 11, fontWeight: 700, color: 'var(--sigap-dark)',
          letterSpacing: '0.07em', textTransform: 'uppercase',
          marginBottom: 28,
        }}>
          <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--sigap)', display: 'inline-block', animation: 'pulse 2s ease-in-out infinite' }} />
          Privacy-by-Design · COMPFEST 18
        </div>

        {/* Headline — bold, kontras */}
        <h1 style={{
          fontFamily: "'Fraunces', Georgia, serif",
          fontSize: 'clamp(38px, 5vw, 58px)',
          fontWeight: 600,
          lineHeight: 1.07,
          letterSpacing: '-0.03em',
          color: 'var(--ink)',
          marginBottom: 20,
        }}>
          Staf yang lebih sigap,<br />
          tanpa perlu{' '}
          <span style={{ color: 'var(--sigap)', fontStyle: 'italic' }}>mengintai.</span>
        </h1>

        {/* Deskripsi */}
        <p style={{
          fontSize: 16,
          color: 'var(--ink-soft)',
          lineHeight: 1.72,
          marginBottom: 36,
          maxWidth: 440,
        }}>
          SAPA membaca gerak tubuh dari rekaman CCTV toko — bukan wajah,
          bukan identitas — untuk{' '}
          <strong style={{ color: 'var(--ink)', fontWeight: 600 }}>menandai pelanggan yang tampak butuh bantuan</strong>,
          dan memberi tahu lebih cepat saat ada yang jatuh.
        </p>

        {/* CTA buttons */}
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          <button id="hero-cta-primary" type="button" onClick={onCTA} style={{
            display: 'inline-flex', alignItems: 'center', gap: 8,
            background: 'var(--sigap)', color: 'white',
            fontSize: 15, fontWeight: 700, fontFamily: 'inherit',
            padding: '13px 28px', borderRadius: 50, border: 'none', cursor: 'pointer',
            boxShadow: '0 4px 20px rgba(47,107,88,0.30)',
            transition: 'all var(--dur-mid) var(--ease)',
            letterSpacing: '-0.01em',
          }}
          onMouseOver={e => { e.currentTarget.style.background='var(--sigap-dark)'; e.currentTarget.style.transform='translateY(-2px)'; e.currentTarget.style.boxShadow='0 8px 28px rgba(47,107,88,0.38)' }}
          onMouseOut={e => { e.currentTarget.style.background='var(--sigap)'; e.currentTarget.style.transform='translateY(0)'; e.currentTarget.style.boxShadow='0 4px 20px rgba(47,107,88,0.30)' }}>
            Coba dengan Video Sendiri
          </button>
          <button id="hero-cta-how" type="button" onClick={onScrollHow} style={{
            display: 'inline-flex', alignItems: 'center', gap: 6,
            background: 'transparent', color: 'var(--ink)',
            fontSize: 15, fontWeight: 600, fontFamily: 'inherit',
            padding: '13px 24px', borderRadius: 50,
            border: '1.5px solid var(--garis)', cursor: 'pointer',
            transition: 'all var(--dur-mid) var(--ease)',
          }}
          onMouseOver={e => { e.currentTarget.style.borderColor='var(--sigap)'; e.currentTarget.style.color='var(--sigap)' }}
          onMouseOut={e => { e.currentTarget.style.borderColor='var(--garis)'; e.currentTarget.style.color='var(--ink)' }}>
            Lihat Cara Kerja ↓
          </button>
        </div>
      </div>

      {/* Kanan — mockup produk */}
      <div style={{ flex: '1 1 360px', display: 'flex', justifyContent: 'center' }}>
        <ProductMockup />
      </div>
    </section>
  )
}

/* ── Stats bar ───────────────────────────────────────────────────────────── */
function StatsBar() {
  const stats = [
    { val: '17',   label: 'titik sendi dianalisis' },
    { val: '0',    label: 'wajah dikenali', accent: true },
    { val: '3 dtk', label: 'jendela deteksi', mono: true },
    { val: '2',    label: 'fitur keselamatan & pelayanan' },
  ]
  return (
    <div style={{
      borderTop: '1px solid var(--garis)',
      borderBottom: '1px solid var(--garis)',
      background: 'var(--paper)',
    }}>
      <div style={{
        maxWidth: 1120, margin: '0 auto',
        display: 'grid',
        gridTemplateColumns: 'repeat(4, 1fr)',
        padding: '0 40px',
      }}>
        {stats.map((s, i) => (
          <div key={i} style={{
            padding: '32px 24px',
            borderRight: i < 3 ? '1px solid var(--garis)' : 'none',
            textAlign: 'center',
          }}>
            <div style={{
              fontFamily: s.mono ? "'IBM Plex Mono', monospace" : "'Fraunces', Georgia, serif",
              fontSize: 38,
              fontWeight: 600,
              letterSpacing: '-0.03em',
              color: s.accent ? 'var(--sigap)' : 'var(--ink)',
              lineHeight: 1,
              marginBottom: 8,
            }}>
              {s.val}
            </div>
            <div style={{ fontSize: 13, color: 'var(--ink-faint)', fontWeight: 500, lineHeight: 1.4 }}>
              {s.label}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

/* ── Section Fitur ─────────────────────────────────────────────────────── */
function FiturSection() {
  return (
    <section style={{ padding: '100px 40px' }}>
      <div style={{ maxWidth: 1120, margin: '0 auto' }}>
        {/* Header */}
        <div style={{ textAlign: 'center', marginBottom: 52 }}>
          <h2 style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontSize: 'clamp(30px, 4vw, 44px)',
            fontWeight: 600,
            letterSpacing: '-0.03em',
            color: 'var(--ink)',
            marginBottom: 14,
          }}>
            Dua hal yang paling sering luput
          </h2>
          <p style={{ fontSize: 16, color: 'var(--ink-soft)', maxWidth: 520, margin: '0 auto', lineHeight: 1.65 }}>
            Staf sibuk, kamera cuma jadi rekaman yang ditonton setelah masalah terjadi.
            SAPA menandainya saat itu juga.
          </p>
        </div>

        {/* 2 kartu */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(380px, 1fr))', gap: 20 }}>
          {/* Fitur Pelayanan */}
          <div style={{
            background: 'var(--surface)',
            border: '1px solid var(--garis)',
            borderRadius: 'var(--radius-xl)',
            padding: '36px 32px',
            boxShadow: 'var(--shadow-sm)',
            transition: 'box-shadow var(--dur-mid)',
          }}
          onMouseOver={e => e.currentTarget.style.boxShadow='var(--shadow-md)'}
          onMouseOut={e => e.currentTarget.style.boxShadow='var(--shadow-sm)'}>
            {/* Tag */}
            <div style={{
              display: 'inline-block',
              fontSize: 10, fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase',
              color: 'var(--bantu-dark)', background: 'var(--bantu-soft)',
              padding: '3px 10px', borderRadius: 4,
              marginBottom: 20,
            }}>
              Fitur Pelayanan
            </div>
            <h3 style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontSize: 22, fontWeight: 600, letterSpacing: '-0.02em',
              color: 'var(--ink)', marginBottom: 14, lineHeight: 1.2,
            }}>
              Pelanggan yang ragu di depan rak
            </h3>
            <p style={{ fontSize: 14, color: 'var(--ink-soft)', lineHeight: 1.75, marginBottom: 24 }}>
              Berdiri lama, menimbang produk berulang kali, tapi tak ada staf yang menghampiri —
              sering berujung pelanggan pergi tanpa membeli.
            </p>
            {/* Visual ilustrasi mini */}
            <div style={{
              borderRadius: 'var(--radius-md)',
              background: 'var(--bantu-soft)',
              border: '1px solid var(--bantu-border)',
              padding: '16px 20px',
              display: 'flex',
              alignItems: 'center',
              gap: 14,
            }}>
              <svg width="40" height="56" viewBox="0 0 40 56" fill="none" aria-hidden="true">
                <circle cx="20" cy="7" r="5.5" stroke="var(--bantu)" strokeWidth="1.8" />
                <line x1="20" y1="12.5" x2="20" y2="30" stroke="var(--bantu)" strokeWidth="1.8" strokeLinecap="round" />
                <line x1="20" y1="19" x2="8"  y2="24" stroke="var(--bantu)" strokeWidth="1.8" strokeLinecap="round" />
                <line x1="20" y1="19" x2="34" y2="22" stroke="var(--bantu)" strokeWidth="1.8" strokeLinecap="round" />
                <line x1="20" y1="30" x2="14" y2="46" stroke="var(--bantu)" strokeWidth="1.8" strokeLinecap="round" />
                <line x1="20" y1="30" x2="26" y2="46" stroke="var(--bantu)" strokeWidth="1.8" strokeLinecap="round" />
                {[[20,12.5],[8,24],[34,22],[14,46],[26,46]].map(([cx,cy],i) => (
                  <circle key={i} cx={cx} cy={cy} r="2.5" fill="var(--bantu)" />
                ))}
              </svg>
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--bantu-dark)', marginBottom: 3 }}>
                  SAPA mendeteksi diam + interaksi tangan
                </div>
                <div style={{ fontSize: 12, color: 'var(--ink-soft)', lineHeight: 1.5 }}>
                  Kamera rak top-down · Model BiLSTM Interaksi
                </div>
              </div>
            </div>
          </div>

          {/* Fitur Keselamatan */}
          <div style={{
            background: 'var(--surface)',
            border: '1px solid var(--garis)',
            borderRadius: 'var(--radius-xl)',
            padding: '36px 32px',
            boxShadow: 'var(--shadow-sm)',
            transition: 'box-shadow var(--dur-mid)',
          }}
          onMouseOver={e => e.currentTarget.style.boxShadow='var(--shadow-md)'}
          onMouseOut={e => e.currentTarget.style.boxShadow='var(--shadow-sm)'}>
            {/* Tag */}
            <div style={{
              display: 'inline-block',
              fontSize: 10, fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase',
              color: 'var(--waspada-dark)', background: 'var(--waspada-soft)',
              padding: '3px 10px', borderRadius: 4,
              marginBottom: 20,
            }}>
              Fitur Keselamatan
            </div>
            <h3 style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontSize: 22, fontWeight: 600, letterSpacing: '-0.02em',
              color: 'var(--ink)', marginBottom: 14, lineHeight: 1.2,
            }}>
              Kejadian jatuh yang telat diketahui
            </h3>
            <p style={{ fontSize: 14, color: 'var(--ink-soft)', lineHeight: 1.75, marginBottom: 24 }}>
              Lorong sepi, tak ada yang melihat langsung — padahal setiap detik penting
              untuk pelanggan lanjut usia atau kondisi darurat.
            </p>
            {/* Visual ilustrasi mini */}
            <div style={{
              borderRadius: 'var(--radius-md)',
              background: 'var(--waspada-soft)',
              border: '1px solid var(--waspada-border)',
              padding: '16px 20px',
              display: 'flex',
              alignItems: 'center',
              gap: 14,
            }}>
              <svg width="60" height="36" viewBox="0 0 60 36" fill="none" aria-hidden="true">
                <circle cx="8"  cy="16" r="5.5" stroke="var(--waspada)" strokeWidth="1.8" />
                <line x1="13"  y1="16" x2="36" y2="16" stroke="var(--waspada)" strokeWidth="1.8" strokeLinecap="round" />
                <line x1="22"  y1="16" x2="22" y2="6"  stroke="var(--waspada)" strokeWidth="1.8" strokeLinecap="round" />
                <line x1="22"  y1="6"  x2="38" y2="4"  stroke="var(--waspada)" strokeWidth="1.8" strokeLinecap="round" />
                <line x1="36"  y1="16" x2="48" y2="28" stroke="var(--waspada)" strokeWidth="1.8" strokeLinecap="round" />
                <line x1="36"  y1="16" x2="50" y2="12" stroke="var(--waspada)" strokeWidth="1.8" strokeLinecap="round" />
                {[[13,16],[22,16],[22,6],[38,4],[48,28],[50,12]].map(([cx,cy],i) => (
                  <circle key={i} cx={cx} cy={cy} r="2.5" fill="var(--waspada)" />
                ))}
              </svg>
              <div>
                <div style={{ fontSize: 12, fontWeight: 700, color: 'var(--waspada-dark)', marginBottom: 3 }}>
                  SAPA mendeteksi perubahan sudut torso
                </div>
                <div style={{ fontSize: 12, color: 'var(--ink-soft)', lineHeight: 1.5 }}>
                  Kamera lorong samping · Model BiLSTM Jatuh
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}

/* ── Cara Kerja ──────────────────────────────────────────────────────────── */
function CaraKerjaSection() {
  const steps = [
    {
      num: '01', title: 'Unggah klip CCTV',
      desc: 'Ambil rekaman dari kamera lorong atau rak. Pilih jenis kamera dan unggah — tidak perlu konfigurasi teknis.',
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="2" y="5" width="15" height="11" rx="1.5" stroke="var(--sigap)" strokeWidth="1.7" />
          <polygon points="17,9 22,7 22,16 17,14" stroke="var(--sigap)" strokeWidth="1.7" strokeLinejoin="round" fill="none" />
        </svg>
      ),
    },
    {
      num: '02', title: 'SAPA membaca gerak tubuh',
      desc: 'AI mengekstrak 17 titik sendi per orang per frame dan menganalisis pola gerak dengan BiLSTM yang dilatih khusus.',
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <circle cx="12" cy="4" r="2.5" stroke="var(--sigap)" strokeWidth="1.7" />
          <line x1="12" y1="6.5" x2="12" y2="13" stroke="var(--sigap)" strokeWidth="1.7" strokeLinecap="round" />
          <line x1="12" y1="9.5" x2="7"  y2="12" stroke="var(--sigap)" strokeWidth="1.7" strokeLinecap="round" />
          <line x1="12" y1="9.5" x2="17" y2="12" stroke="var(--sigap)" strokeWidth="1.7" strokeLinecap="round" />
          <line x1="12" y1="13" x2="9"  y2="19" stroke="var(--sigap)" strokeWidth="1.7" strokeLinecap="round" />
          <line x1="12" y1="13" x2="15" y2="19" stroke="var(--sigap)" strokeWidth="1.7" strokeLinecap="round" />
          {[[12,6.5],[7,12],[17,12],[9,19],[15,19]].map(([cx,cy],i) =>
            <circle key={i} cx={cx} cy={cy} r="1.8" fill="var(--sigap)" />
          )}
        </svg>
      ),
    },
    {
      num: '03', title: 'Lihat hasilnya',
      desc: 'Video beranotasi + timeline kejadian. Klik tiap kejadian untuk langsung lompat ke momen tersebut di video.',
      icon: (
        <svg width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <rect x="2" y="4" width="20" height="16" rx="2" stroke="var(--sigap)" strokeWidth="1.7" />
          <line x1="2" y1="9"  x2="22" y2="9"  stroke="var(--garis)" strokeWidth="1" />
          <rect x="4"  y="11.5" width="3.5" height="5.5" rx="0.8" fill="var(--bantu)"   opacity="0.8" />
          <rect x="10" y="13"   width="3.5" height="4"   rx="0.8" fill="var(--waspada)" opacity="0.8" />
          <rect x="16" y="11"   width="3.5" height="6"   rx="0.8" fill="var(--sigap)"   opacity="0.8" />
        </svg>
      ),
    },
  ]
  return (
    <section id="cara-kerja" style={{
      padding: '80px 40px 100px',
      background: 'var(--paper-2)',
      borderTop: '1px solid var(--garis)',
    }}>
      <div style={{ maxWidth: 1120, margin: '0 auto' }}>
        <div style={{ marginBottom: 56, maxWidth: 520 }}>
          <div style={{ fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--sigap)', marginBottom: 14 }}>
            Cara Kerja
          </div>
          <h2 style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontSize: 'clamp(28px, 3.5vw, 38px)',
            fontWeight: 600, letterSpacing: '-0.02em', color: 'var(--ink)',
          }}>
            Tiga langkah, satu klip video
          </h2>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: 2 }}>
          {steps.map((step, i) => (
            <div key={i} style={{
              background: 'var(--surface)',
              borderRadius: 'var(--radius-lg)',
              padding: '32px 28px',
              marginRight: i < 2 ? 0 : 0,
              border: '1px solid var(--garis)',
              borderRight: i < 2 ? 'none' : '1px solid var(--garis)',
              borderRadius: i === 0 ? '14px 0 0 14px' : i === 2 ? '0 14px 14px 0' : '0',
              position: 'relative',
            }}>
              {/* Nomor */}
              <div style={{
                fontFamily: "'IBM Plex Mono', monospace",
                fontSize: 11, fontWeight: 700, color: 'var(--sigap)',
                letterSpacing: '0.08em', marginBottom: 18,
              }}>
                {step.num}
              </div>
              {/* Ikon */}
              <div style={{
                width: 48, height: 48, borderRadius: 12,
                background: 'var(--sigap-soft)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                marginBottom: 20,
              }}>
                {step.icon}
              </div>
              <h3 style={{
                fontSize: 17, fontWeight: 700, color: 'var(--ink)',
                marginBottom: 10, letterSpacing: '-0.01em',
              }}>
                {step.title}
              </h3>
              <p style={{ fontSize: 14, color: 'var(--ink-soft)', lineHeight: 1.7 }}>
                {step.desc}
              </p>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

/* ── Teaser Live ─────────────────────────────────────────────────────────── */
function LiveTeaserSection({ onLive }) {
  return (
    <div style={{ padding: '0 40px 80px' }}>
      <div style={{
        maxWidth: 1120, margin: '0 auto',
        padding: '24px 32px',
        borderRadius: 'var(--radius-xl)',
        background: 'var(--surface)',
        border: '1px solid var(--garis)',
        display: 'flex', alignItems: 'center', gap: 20, flexWrap: 'wrap',
        boxShadow: 'var(--shadow-xs)',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexShrink: 0 }}>
          <span style={{
            width: 9, height: 9, borderRadius: '50%',
            background: 'var(--waspada)', boxShadow: '0 0 6px var(--waspada)',
            animation: 'pulse 1.5s ease-in-out infinite', display: 'inline-block',
          }} />
          <span style={{ fontSize: 11, fontWeight: 800, letterSpacing: '0.1em', textTransform: 'uppercase', color: 'var(--waspada)' }}>
            Mode Live (Demo)
          </span>
        </div>
        <p style={{ flex: 1, fontSize: 14, color: 'var(--ink-soft)', minWidth: 200, lineHeight: 1.55 }}>
          Analisis langsung dari webcam atau kamera IP — pipeline yang sama persis, tanpa upload file.
        </p>
        <button id="live-teaser-btn" type="button" onClick={onLive}
          style={{
            background: 'none', border: '1.5px solid var(--garis)',
            borderRadius: 50, color: 'var(--ink-soft)',
            fontSize: 13, fontWeight: 600, fontFamily: 'inherit',
            padding: '8px 20px', cursor: 'pointer', flexShrink: 0,
            transition: 'all var(--dur-fast)',
          }}
          onMouseOver={e => { e.currentTarget.style.borderColor='var(--sigap)'; e.currentTarget.style.color='var(--sigap)' }}
          onMouseOut={e => { e.currentTarget.style.borderColor='var(--garis)'; e.currentTarget.style.color='var(--ink-soft)' }}>
          Coba Mode Live →
        </button>
      </div>
    </div>
  )
}

/* ── Privasi ─────────────────────────────────────────────────────────────── */
function PrivasiSection() {
  const poin = [
    {
      title: 'Pose-only, bukan wajah',
      desc: 'Secara arsitektur, SAPA hanya memproses koordinat sendi. Tidak ada modul pengenalan wajah.',
      icon: (
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <circle cx="9" cy="5" r="3" stroke="white" strokeWidth="1.5" />
          <line x1="9" y1="8"  x2="9" y2="14" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="9" y1="11" x2="5" y2="13" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="9" y1="11" x2="13" y2="13" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="9" y1="14" x2="7" y2="17" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="9" y1="14" x2="11" y2="17" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      ),
    },
    {
      title: 'Video tidak disimpan permanen',
      desc: 'File video dihapus otomatis setelah diproses. Hanya metadata kejadian yang disimpan.',
      icon: (
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <path d="M9 1.5L2 4.5v4.5c0 4 2.8 7.5 7 9 4.2-1.5 7-5 7-9V4.5L9 1.5z" stroke="white" strokeWidth="1.5" fill="none" strokeLinejoin="round" />
          <polyline points="6,9 8,11 12,7" stroke="white" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      ),
    },
    {
      title: 'Bisa dijalankan on-premise',
      desc: 'Seluruh sistem bisa dipasang di server toko sendiri — video mentah tidak keluar dari lokasi.',
      icon: (
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <rect x="2" y="8" width="14" height="8" rx="1.5" stroke="white" strokeWidth="1.5" />
          <path d="M5 8V5.5a4 4 0 018 0V8" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
          <circle cx="9" cy="12.5" r="1.2" fill="white" opacity="0.8" />
        </svg>
      ),
    },
    {
      title: '"AI menandai, manusia memutuskan"',
      desc: 'Setiap alert hanya rekomendasi untuk staf. Human-in-the-loop adalah arsitektur, bukan fitur.',
      icon: (
        <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
          <circle cx="9" cy="9" r="7" stroke="white" strokeWidth="1.5" />
          <line x1="9" y1="5" x2="9"  y2="9"  stroke="white" strokeWidth="1.5" strokeLinecap="round" />
          <line x1="9" y1="9" x2="12" y2="12" stroke="white" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      ),
    },
  ]

  return (
    <section id="privasi" style={{ padding: '100px 40px', background: 'var(--sigap)' }}>
      <div style={{ maxWidth: 1120, margin: '0 auto' }}>
        <div style={{
          display: 'grid',
          gridTemplateColumns: '1fr 1fr',
          gap: 64,
          alignItems: 'center',
        }}>
          {/* Kiri — teks header */}
          <div>
            <div style={{
              fontSize: 11, fontWeight: 700, letterSpacing: '0.1em', textTransform: 'uppercase',
              color: 'rgba(255,255,255,0.55)', marginBottom: 18,
            }}>
              Privasi & Governance
            </div>
            <h2 style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontSize: 'clamp(30px, 4vw, 44px)',
              fontWeight: 600, letterSpacing: '-0.03em',
              color: 'white', marginBottom: 20, lineHeight: 1.1,
            }}>
              Privasi bukan pilihan — ini arsitekturnya.
            </h2>
            <p style={{ fontSize: 16, color: 'rgba(255,255,255,0.72)', lineHeight: 1.75, marginBottom: 32 }}>
              Privacy-by-design bukan fitur yang bisa dinonaktifkan di SAPA.
              Sistem tidak pernah mencoba mengenali siapa yang ada di video.
            </p>
            {/* UU PDP note */}
            <div style={{
              display: 'inline-flex', alignItems: 'center', gap: 8,
              background: 'rgba(255,255,255,0.12)', border: '1px solid rgba(255,255,255,0.18)',
              borderRadius: 8, padding: '10px 16px',
              fontSize: 13, color: 'rgba(255,255,255,0.8)',
            }}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="6" stroke="rgba(255,255,255,0.7)" strokeWidth="1.2" />
                <line x1="7" y1="4" x2="7" y2="7" stroke="rgba(255,255,255,0.7)" strokeWidth="1.2" strokeLinecap="round" />
                <circle cx="7" cy="9.5" r="0.7" fill="rgba(255,255,255,0.7)" />
              </svg>
              Selaras prinsip UU PDP Indonesia
            </div>
          </div>

          {/* Kanan — 4 poin */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
            {poin.map((p, i) => (
              <div key={i} style={{
                display: 'flex', gap: 14, alignItems: 'flex-start',
                padding: '18px 20px',
                borderRadius: 'var(--radius-md)',
                background: 'rgba(255,255,255,0.09)',
                border: '1px solid rgba(255,255,255,0.13)',
                backdropFilter: 'blur(8px)',
              }}>
                <div style={{
                  width: 36, height: 36, borderRadius: 10,
                  background: 'rgba(255,255,255,0.15)',
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  flexShrink: 0,
                }}>
                  {p.icon}
                </div>
                <div>
                  <div style={{ fontSize: 14, fontWeight: 700, color: 'white', marginBottom: 4, lineHeight: 1.3 }}>
                    {p.title}
                  </div>
                  <div style={{ fontSize: 13, color: 'rgba(255,255,255,0.65)', lineHeight: 1.6 }}>
                    {p.desc}
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  )
}

/* ── CTA Final ───────────────────────────────────────────────────────────── */
function CTAFinal({ onCTA }) {
  return (
    <section style={{ padding: '100px 40px', textAlign: 'center' }}>
      <div style={{ maxWidth: 560, margin: '0 auto' }}>
        <h2 style={{
          fontFamily: "'Fraunces', Georgia, serif",
          fontSize: 'clamp(32px, 4.5vw, 50px)',
          fontWeight: 600, letterSpacing: '-0.03em',
          color: 'var(--ink)', lineHeight: 1.08, marginBottom: 18,
        }}>
          Siap mencoba dengan video Anda sendiri?
        </h2>
        <p style={{ fontSize: 16, color: 'var(--ink-soft)', lineHeight: 1.7, marginBottom: 40 }}>
          Unggah klip .mp4 dari CCTV toko. SAPA mengembalikan video beranotasi
          + timeline kejadian dalam hitungan menit.
        </p>
        <button id="final-cta-btn" type="button" onClick={onCTA} style={{
          display: 'inline-flex', alignItems: 'center', gap: 8,
          background: 'var(--sigap)', color: 'white',
          fontSize: 17, fontWeight: 700, fontFamily: 'inherit',
          padding: '16px 44px', borderRadius: 50, border: 'none', cursor: 'pointer',
          boxShadow: '0 4px 24px rgba(47,107,88,0.30)',
          transition: 'all var(--dur-mid) var(--ease)',
          letterSpacing: '-0.01em',
        }}
        onMouseOver={e => { e.currentTarget.style.background='var(--sigap-dark)'; e.currentTarget.style.transform='translateY(-2px)' }}
        onMouseOut={e => { e.currentTarget.style.background='var(--sigap)'; e.currentTarget.style.transform='translateY(0)' }}>
          Mulai Analisis Sekarang →
        </button>
        <div style={{ marginTop: 16, fontSize: 12, color: 'var(--ink-faint)' }}>
          Gratis · Tanpa akun · Video dihapus setelah diproses
        </div>
      </div>
    </section>
  )
}

/* ── Footer ──────────────────────────────────────────────────────────────── */
function Footer() {
  return (
    <footer style={{
      padding: '24px 40px',
      borderTop: '1px solid var(--garis)',
      background: 'var(--paper-2)',
      display: 'flex', justifyContent: 'space-between', alignItems: 'center',
      flexWrap: 'wrap', gap: 10,
    }}>
      <span style={{ fontSize: 12, color: 'var(--ink-faint)' }}>
        <strong style={{ color: 'var(--ink-soft)' }}>SAPA</strong> — Safety and Assistance through Pose Analytics
      </span>
      <span style={{ fontSize: 12, color: 'var(--ink-faint)' }}>
        AI Innovation Challenge · COMPFEST 18 · Privacy-by-Design
      </span>
    </footer>
  )
}

/* ── Landing Page utama ──────────────────────────────────────────────────── */
export default function LandingPage() {
  const navigate = useNavigate()

  const goCTA    = () => navigate('/analisis')
  const goLive   = () => navigate('/live')
  const scrollHow = () =>
    document.getElementById('cara-kerja')?.scrollIntoView({ behavior: 'smooth' })

  return (
    <div style={{ background: 'var(--paper)', minHeight: '100vh' }}>
      <LandingNav onCTA={goCTA} onLive={goLive} />
      <HeroSection    onCTA={goCTA} onScrollHow={scrollHow} />
      <StatsBar />
      <FiturSection />
      <CaraKerjaSection />
      <LiveTeaserSection onLive={goLive} />
      <PrivasiSection />
      <CTAFinal onCTA={goCTA} />
      <Footer />
    </div>
  )
}
