"""
production/buffer.py — SAPA Produksi

Buffer jendela geser per-orang yang berjalan kontinu (KONTEKS §4 poin 2).

PERBEDAAN PENTING DARI MVP OFFLINE
----------------------------------
Di MVP, seluruh video tersedia sekaligus: build_windows_for_heads() menerima
[T,17,3] utuh lalu memotongnya menjadi W jendela. Di produksi tidak ada "seluruh
video" — frame datang satu per satu, selamanya. Buffer ini yang menjembatani.

JENDELA DIUKUR DALAM DETIK, BUKAN JUMLAH FRAME
----------------------------------------------
Kedua kepala BiLSTM dilatih pada jendela 3 detik @15fps = 45 frame. Menyimpan
"45 frame terakhir" hanya benar bila laju proses tepat 15fps — dan di produksi
itu tidak pernah terjadi: laju nyata bergantung beban GPU, jumlah orang, dan
kondisi jaringan, serta berubah-ubah dalam satu sesi.

Menyimpan 45 frame pada laju 5fps berarti buffer memuat 9 DETIK kejadian, yang
lalu di-resample menjadi 135 frame dan menghasilkan 3 jendela — dan jendela
pertama (yang biasanya diambil) menggambarkan kejadian 6 detik yang lalu. Untuk
deteksi jatuh, alert sebasi itu tidak ada gunanya.

Karena itu buffer di sini menyimpan (waktu, keypoints) dan memotong jendela
berdasarkan RENTANG WAKTU. `src_fps` dihitung dari stempel waktu nyata isi
jendela, lalu diserahkan ke build_windows_for_heads() yang me-resample ke 45
frame @15fps persis seperti saat training.

PENANGANAN GAP (KONTEKS §9.3)
-----------------------------
Di toko nyata pose terputus: orang tertutup rak, melewati area gelap, atau YOLO
kehilangan deteksi sesaat. Menyambung begitu saja frame sebelum dan sesudah
occlusion 4 detik akan menghasilkan "lompatan" gerak palsu yang terbaca seperti
jatuh. Jeda melebihi `max_gap_seconds` karena itu MENGOSONGKAN buffer track
tersebut — lebih baik kehilangan satu jendela daripada mengarang gerakan.
"""

import logging
import threading
from collections import deque
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class TrackWindow:
    """Satu jendela siap-inferensi untuk satu orang."""

    track_id: int
    frames: np.ndarray      # [T, 17, 3] koordinat piksel MENTAH
    src_fps: float          # laju efektif isi jendela ini (dari stempel waktu nyata)
    t_mulai: float          # monotonic, detik
    t_selesai: float        # monotonic, detik

    @property
    def n_frames(self) -> int:
        return int(self.frames.shape[0])

    @property
    def durasi(self) -> float:
        return self.t_selesai - self.t_mulai


class TrackWindowBuffer:
    """
    Menyimpan sekuens keypoint per track_id dan memancarkan jendela siap-inferensi.

    Aman dipakai dari beberapa thread. Satu instance per kamera — track_id hanya
    unik dalam satu stream (KONTEKS §9.6: SAPA tidak melakukan re-identifikasi
    lintas kamera, dan memang tidak perlu — alert cukup dipicu per kamera).
    """

    def __init__(
        self,
        window_seconds: float = 3.0,
        stride_seconds: float = 1.0,
        max_gap_seconds: float = 1.0,
        track_ttl_seconds: float = 5.0,
        min_frames: int = 12,
    ):
        self.window_seconds = float(window_seconds)
        self.stride_seconds = float(stride_seconds)
        self.max_gap_seconds = float(max_gap_seconds)
        self.track_ttl_seconds = float(track_ttl_seconds)
        self.min_frames = int(min_frames)

        # Simpan sedikit lebih panjang dari satu jendela agar pemotongan
        # berbasis waktu tidak kehabisan sampel di tepi.
        self._simpan_detik = self.window_seconds * 1.5

        self._lock = threading.Lock()
        # {track_id: deque[(t, kps[17,3])]}
        self._data: dict[int, deque] = {}
        # {track_id: t saat jendela terakhir dipancarkan}
        self._pancar_terakhir: dict[int, float] = {}
        self._n_gap = 0

    # ── Masukan ───────────────────────────────────────────────────────────────
    def push(self, track_id: int, keypoints: np.ndarray, t: float) -> None:
        """
        Tambahkan satu sampel pose. `t` = detik monotonic saat frame diambil.
        Buffer track direset bila jeda dari sampel sebelumnya > max_gap_seconds.
        """
        with self._lock:
            buf = self._data.get(track_id)
            if buf is None:
                buf = deque()
                self._data[track_id] = buf
            elif buf and (t - buf[-1][0]) > self.max_gap_seconds:
                # Sekuens terputus — buang, jangan sambung melintasi occlusion.
                jeda = t - buf[-1][0]
                buf.clear()
                self._pancar_terakhir.pop(track_id, None)
                self._n_gap += 1
                logger.debug(
                    f"[buffer] track={track_id} direset (jeda {jeda:.1f}s "
                    f"> {self.max_gap_seconds:.1f}s)"
                )

            buf.append((float(t), np.asarray(keypoints, dtype=np.float32).copy()))

            # Buang sampel yang sudah lewat masa simpan.
            batas = t - self._simpan_detik
            while buf and buf[0][0] < batas:
                buf.popleft()

    # ── Keluaran ──────────────────────────────────────────────────────────────
    def jendela_siap(self) -> list[TrackWindow]:
        """
        Ambil semua jendela yang siap diinferensi, lalu tandai sudah dipancarkan.

        Sebuah track siap bila:
          - rentang waktu isinya sudah >= window_seconds, DAN
          - sudah >= stride_seconds sejak jendela terakhirnya dipancarkan, DAN
          - jumlah sampel di dalam jendela >= min_frames (tahan occlusion sesaat).
        """
        hasil: list[TrackWindow] = []

        with self._lock:
            for tid, buf in self._data.items():
                if len(buf) < 2:
                    continue

                t_awal_buf = buf[0][0]
                t_akhir_buf = buf[-1][0]

                if (t_akhir_buf - t_awal_buf) < self.window_seconds:
                    continue

                terakhir = self._pancar_terakhir.get(tid)
                if terakhir is not None and (t_akhir_buf - terakhir) < self.stride_seconds:
                    continue

                # Potong berdasarkan waktu: window_seconds terakhir.
                batas = t_akhir_buf - self.window_seconds
                sampel = [(t, k) for (t, k) in buf if t >= batas]

                if len(sampel) < self.min_frames:
                    continue

                waktu = np.array([s[0] for s in sampel], dtype=np.float64)
                span = float(waktu[-1] - waktu[0])
                if span <= 1e-6:
                    continue

                # Laju efektif NYATA jendela ini — inilah yang membuat
                # resampling di build_windows_for_heads() benar.
                src_fps = (len(sampel) - 1) / span

                frames = np.stack([s[1] for s in sampel], axis=0).astype(np.float32)

                hasil.append(
                    TrackWindow(
                        track_id=tid,
                        frames=frames,
                        src_fps=src_fps,
                        t_mulai=float(waktu[0]),
                        t_selesai=float(waktu[-1]),
                    )
                )
                self._pancar_terakhir[tid] = t_akhir_buf

        return hasil

    # ── Perawatan ─────────────────────────────────────────────────────────────
    def bersihkan(self, sekarang: float) -> int:
        """
        Lupakan track yang sudah tidak terlihat melebihi TTL.

        Wajib dipanggil berkala: tanpa ini, proses yang berjalan berbulan-bulan
        akan mengumpulkan puluhan ribu track_id mati dan memakan memori terus.
        """
        with self._lock:
            mati = [
                tid for tid, buf in self._data.items()
                if not buf or (sekarang - buf[-1][0]) > self.track_ttl_seconds
            ]
            for tid in mati:
                del self._data[tid]
                self._pancar_terakhir.pop(tid, None)
        return len(mati)

    def lupakan(self, track_id: int) -> None:
        with self._lock:
            self._data.pop(track_id, None)
            self._pancar_terakhir.pop(track_id, None)

    def kosongkan(self) -> None:
        with self._lock:
            self._data.clear()
            self._pancar_terakhir.clear()

    # ── Introspeksi ───────────────────────────────────────────────────────────
    @property
    def jumlah_track(self) -> int:
        with self._lock:
            return len(self._data)

    def statistik(self) -> dict:
        with self._lock:
            return {
                "track_aktif": len(self._data),
                "sampel_total": sum(len(b) for b in self._data.values()),
                "reset_karena_gap": self._n_gap,
            }
