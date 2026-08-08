"""
production/stream.py — SAPA Produksi

Konektor stream kamera yang tahan 24/7 (KONTEKS §4 poin 1).

Tiga masalah nyata yang diselesaikan di sini — tidak satu pun muncul di MVP
offline, karena membaca berkas .mp4 tidak pernah gagal di tengah jalan:

1. PUTUS KONEKSI. Kamera IP mati, kabel dicabut, switch reboot. Pembaca harus
   menyambung ulang sendiri dengan backoff eksponensial, bukan mematikan proses.

2. LATENSI MENUMPUK. VideoCapture pada RTSP mengantre frame di buffer internal.
   Kalau konsumen lebih lambat dari kamera, antrean tumbuh dan alert makin basi
   — persis kebalikan dari yang dibutuhkan deteksi jatuh. Solusinya "frame
   terbaru menang": pembaca membuang frame lama, konsumen selalu dapat yang
   paling baru.

3. BIAYA DECODE. Kamera 25fps sementara kita hanya butuh 8fps untuk inferensi.
   Men-decode 25 frame lalu membuang 17 itu pemborosan CPU besar per kamera.
   Karena itu dipakai pasangan grab()/retrieve(): grab() memajukan stream tanpa
   men-decode (murah), retrieve() baru men-decode frame yang benar-benar dipakai.

Catatan RTSP: transport dipaksa ke TCP. Default UDP kehilangan paket pada
jaringan toko yang sibuk dan menghasilkan frame rusak/artefak yang membuat pose
kacau — TCP lebih lambat sedikit tapi jauh lebih stabil.
"""

import logging
import os
import threading
import time

import numpy as np

logger = logging.getLogger(__name__)

# Harus di-set SEBELUM cv2.VideoCapture pertama dibuat agar terbaca FFmpeg.
os.environ.setdefault(
    "OPENCV_FFMPEG_CAPTURE_OPTIONS",
    "rtsp_transport;tcp|stimeout;5000000",   # stimeout dalam mikrodetik = 5 dtk
)

import cv2  # noqa: E402  — impor setelah env FFmpeg di atas


_SKEMA_JARINGAN = ("rtsp://", "rtsps://", "http://", "https://", "rtmp://")


def _parse_sumber(sumber: str):
    """Ubah "0" menjadi indeks webcam int; sisanya diteruskan apa adanya."""
    s = str(sumber).strip()
    if s.isdigit():
        return int(s)
    return s


def _sumber_berkas(sumber: str) -> bool:
    """
    True bila sumber adalah berkas video di disk, bukan kamera langsung.

    Berkas dipakai untuk demo/uji lapangan tanpa kamera fisik. Perilakunya harus
    berbeda dari stream langsung: berkas tidak "menahan" grab() sesuai waktu
    nyata, jadi tanpa penjadwalan loop akan melahap seluruh berkas dalam
    hitungan detik dan membakar satu inti CPU penuh.
    """
    s = str(sumber).strip()
    if s.isdigit():
        return False
    return not s.lower().startswith(_SKEMA_JARINGAN)


class FrameGrabber:
    """
    Pembaca frame satu kamera, berjalan di thread sendiri.

    Pemakaian:
        g = FrameGrabber("rtsp://...", nama="kasir-1", target_fps=8)
        g.start()
        hasil = g.read()          # (frame BGR, t_monotonic) atau None bila belum ada
        ...
        g.stop()

    read() bersifat non-blocking dan mengembalikan frame TERBARU. Memanggilnya
    dua kali tanpa jeda bisa mengembalikan frame yang sama — konsumen wajib
    memeriksa nomor urut lewat read_baru() bila butuh frame unik.
    """

    def __init__(
        self,
        sumber: str,
        nama: str = "kamera",
        target_fps: float = 8.0,
        reconnect_delay: float = 2.0,
        reconnect_max_delay: float = 30.0,
        ulang_berkas: bool = True,
    ):
        self.sumber = sumber
        self.nama = nama
        self.target_fps = max(0.5, float(target_fps))
        self.reconnect_delay = reconnect_delay
        self.reconnect_max_delay = reconnect_max_delay
        self.ulang_berkas = ulang_berkas

        self._interval = 1.0 / self.target_fps
        self._berkas = _sumber_berkas(sumber)
        # Jeda antar grab() untuk sumber berkas, agar berjalan sesuai waktu nyata.
        # Diisi dari FPS berkas saat dibuka.
        self._jeda_grab = 0.0

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

        self._frame: np.ndarray | None = None
        self._frame_t: float = 0.0
        self._seq: int = 0

        # Statistik kesehatan
        self._terhubung = False
        self._n_decode = 0
        self._n_buang = 0
        self._n_reconnect = 0
        self._error_terakhir: str | None = None
        self._t_terhubung: float | None = None
        self._fps_terukur = 0.0
        self._fps_penanda_t = 0.0
        self._fps_penanda_n = 0

    # ── Siklus hidup ──────────────────────────────────────────────────────────
    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._loop, name=f"grabber-{self.nama}", daemon=True
        )
        self._thread.start()
        logger.info(f"[stream:{self.nama}] Pembaca dimulai.")

    def stop(self, timeout: float = 5.0) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive():
            t.join(timeout=timeout)
        self._thread = None
        logger.info(f"[stream:{self.nama}] Pembaca dihentikan.")

    # ── Konsumsi ──────────────────────────────────────────────────────────────
    def read(self) -> tuple[np.ndarray, float] | None:
        """Frame terbaru + stempel waktu monotonic, atau None bila belum ada."""
        with self._lock:
            if self._frame is None:
                return None
            return self._frame, self._frame_t

    def read_baru(self, seq_terakhir: int) -> tuple[np.ndarray, float, int] | None:
        """
        Seperti read(), tapi hanya mengembalikan frame bila nomor urutnya lebih
        baru dari `seq_terakhir`. Mencegah pekerja memproses frame yang sama dua
        kali saat kamera lebih lambat dari laju loop.
        """
        with self._lock:
            if self._frame is None or self._seq <= seq_terakhir:
                return None
            return self._frame, self._frame_t, self._seq

    # ── Kesehatan ─────────────────────────────────────────────────────────────
    @property
    def terhubung(self) -> bool:
        return self._terhubung

    def kesehatan(self) -> dict:
        with self._lock:
            umur = (time.monotonic() - self._frame_t) if self._frame_t else None
        return {
            "terhubung": self._terhubung,
            "fps_terukur": round(self._fps_terukur, 2),
            "umur_frame_detik": round(umur, 2) if umur is not None else None,
            "frame_didecode": self._n_decode,
            "frame_dibuang": self._n_buang,
            "jumlah_reconnect": self._n_reconnect,
            "error_terakhir": self._error_terakhir,
            "uptime_detik": (
                round(time.monotonic() - self._t_terhubung, 1)
                if self._t_terhubung else None
            ),
        }

    # ── Internal ──────────────────────────────────────────────────────────────
    def _buka(self):
        """Buka VideoCapture. Kembalikan cap terbuka atau None."""
        target = _parse_sumber(self.sumber)
        cap = cv2.VideoCapture(target)
        if not cap.isOpened():
            cap.release()
            return None
        # Buffer sekecil mungkin — kita mau frame terbaru, bukan antrean.
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass  # tidak semua backend mendukung; bukan kegagalan fatal

        if self._berkas:
            fps_berkas = cap.get(cv2.CAP_PROP_FPS) or 25.0
            self._jeda_grab = 1.0 / max(1.0, fps_berkas)
        return cap

    def _loop(self) -> None:
        cap = None
        jeda = self.reconnect_delay
        t_retrieve_terakhir = 0.0

        while not self._stop.is_set():
            # ── Sambungkan / sambung ulang ────────────────────────────────────
            if cap is None:
                cap = self._buka()
                if cap is None:
                    self._terhubung = False
                    self._error_terakhir = "gagal membuka sumber"
                    self._n_reconnect += 1
                    logger.warning(
                        f"[stream:{self.nama}] Gagal membuka sumber — "
                        f"coba lagi dalam {jeda:.0f} dtk."
                    )
                    # Tidur sambil tetap responsif terhadap stop()
                    if self._stop.wait(jeda):
                        break
                    jeda = min(jeda * 2, self.reconnect_max_delay)
                    continue

                self._terhubung = True
                self._error_terakhir = None
                self._t_terhubung = time.monotonic()
                self._fps_penanda_t = time.monotonic()
                self._fps_penanda_n = self._n_decode
                jeda = self.reconnect_delay      # backoff direset setelah sukses
                logger.info(f"[stream:{self.nama}] Terhubung.")

            # ── Majukan stream tanpa decode (murah) ───────────────────────────
            try:
                ok = cap.grab()
            except Exception as e:
                ok = False
                self._error_terakhir = f"grab error: {e}"

            if not ok and self._berkas and self.ulang_berkas:
                # Berkas demo habis — putar ulang dari awal. Ini bukan gangguan,
                # jadi tidak dihitung sebagai reconnect dan tanpa backoff.
                try:
                    cap.release()
                except Exception:
                    pass
                cap = None
                continue

            if not ok:
                logger.warning(f"[stream:{self.nama}] Stream terputus — menyambung ulang.")
                self._terhubung = False
                self._error_terakhir = self._error_terakhir or "stream terputus"
                try:
                    cap.release()
                except Exception:
                    pass
                cap = None
                self._n_reconnect += 1
                if self._stop.wait(jeda):
                    break
                jeda = min(jeda * 2, self.reconnect_max_delay)
                continue

            # Sumber berkas tidak menahan grab() sesuai waktu nyata — tahan di
            # sini agar berkas demo berjalan dengan kecepatan aslinya.
            if self._berkas and self._jeda_grab > 0:
                if self._stop.wait(self._jeda_grab):
                    break

            # ── Decode hanya bila sudah waktunya ──────────────────────────────
            sekarang = time.monotonic()
            if sekarang - t_retrieve_terakhir < self._interval:
                self._n_buang += 1
                continue

            try:
                ok, frame = cap.retrieve()
            except Exception as e:
                ok, frame = False, None
                self._error_terakhir = f"retrieve error: {e}"

            if not ok or frame is None:
                self._n_buang += 1
                continue

            t_retrieve_terakhir = sekarang
            with self._lock:
                self._frame = frame
                self._frame_t = sekarang
                self._seq += 1
            self._n_decode += 1

            # FPS terukur — rata-rata bergulir tiap ~5 detik
            if sekarang - self._fps_penanda_t >= 5.0:
                selisih_n = self._n_decode - self._fps_penanda_n
                selisih_t = sekarang - self._fps_penanda_t
                self._fps_terukur = selisih_n / selisih_t if selisih_t > 0 else 0.0
                self._fps_penanda_t = sekarang
                self._fps_penanda_n = self._n_decode

        # ── Bersih-bersih ─────────────────────────────────────────────────────
        if cap is not None:
            try:
                cap.release()
            except Exception:
                pass
        self._terhubung = False
