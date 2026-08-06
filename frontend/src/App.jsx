import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import LandingPage from './pages/LandingPage.jsx'
import LivePage from './pages/LivePage.jsx'
import AnalisisApp from './AnalisisApp.jsx'

/* ─────────────────────────────────────────────────────────────────────────────
   App — router utama
   /          → Landing Page
   /analisis  → Alur unggah/proses/hasil (submission inti)
   /live      → Mode Live Demo (WebSocket webcam)
───────────────────────────────────────────────────────────────────────────── */
export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/"         element={<LandingPage />} />
        <Route path="/analisis" element={<AnalisisApp />} />
        <Route path="/live"     element={<LivePage />} />
        {/* Fallback — redirect ke landing */}
        <Route path="*"         element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
