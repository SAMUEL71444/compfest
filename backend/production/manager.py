"""
production/manager.py — SAPA Produksi

Manajemen multi-kamera (KONTEKS §4 poin 4).

Satu toko = banyak kamera dengan sudut berbeda: beberapa lorong (Kepala Jatuh)
dan beberapa rak (Kepala Interaksi). Manajer inilah yang menyalakan, mematikan,
dan mengawasi pekerja per kamera, serta menyimpan satu-satunya salinan model
BiLSTM yang dibagi ke semua pekerja.

MODEL DIMUAT SEKALI, DIBAGI KE SEMUA KAMERA
-------------------------------------------
Dua kepala BiLSTM sangat ringan (~408k parameter, ~0,12 ms per jendela), jadi
menyalinnya per kamera hanya memboroskan RAM tanpa menambah throughput.
Yang TIDAK dibagi adalah YOLO — lihat catatan di worker.py soal state ByteTrack.

PEMANTAUAN KESEHATAN
--------------------
Thread pengawas memeriksa tiap kamera secara berkala. Pekerja yang mati karena
kesalahan tak terduga dinyalakan ulang otomatis; sistem yang dipasang di toko
tidak boleh butuh operator untuk hidup lagi setelah satu kamera bermasalah.
Pengawas ini juga yang menjalankan retensi log kejadian (§7).
"""

import logging
import threading
import time
from pathlib import Path

from .alerts import AlertEngine, EventLog
from .profiles import CameraProfile, ProfileStore
from .worker import CameraWorker

logger = logging.getLogger(__name__)


class CameraManager:
    """Pengelola seluruh kamera produksi. Satu instance per proses."""

    def __init__(
        self,
        path_profil: str | Path,
        path_log_kejadian: str | Path | None = None,
        retensi_jam: float = 72.0,
        interval_pengawas: float = 15.0,
    ):
        self.store = ProfileStore(path_profil)
        self.log = EventLog(retensi_jam=retensi_jam, path_jsonl=path_log_kejadian)
        self.alert = AlertEngine(self.log)

        self._lock = threading.RLock()
        self._workers: dict[str, CameraWorker] = {}

        # Dibagi ke semua pekerja (lihat docstring modul).
        self._fall_model = None
        self._inter_model = None
        self._kunci_inferensi = threading.Lock()

        self._interval_pengawas = interval_pengawas
        self._pengawas: threading.Thread | None = None
        self._stop_pengawas = threading.Event()
        self._t_purge_terakhir = 0.0

    # ── Model ─────────────────────────────────────────────────────────────────
    def pasang_model(self, fall_model=None, inter_model=None) -> None:
        """Dipanggil saat startup app dengan model yang sudah dimuat app.py."""
        with self._lock:
            self._fall_model = fall_model
            self._inter_model = inter_model

    # ── Siklus hidup sistem ───────────────────────────────────────────────────
    def mulai(self) -> None:
        """Nyalakan semua kamera bertanda aktif, lalu jalankan pengawas."""
        for p in self.store.semua():
            if p.aktif:
                try:
                    self.mulai_kamera(p.id)
                except Exception as e:
                    logger.error(f"[manajer] Gagal memulai '{p.id}': {e}")

        self._stop_pengawas.clear()
        self._pengawas = threading.Thread(
            target=self._loop_pengawas, name="pengawas-kamera", daemon=True
        )
        self._pengawas.start()
        logger.info(f"[manajer] Sistem produksi aktif — {len(self._workers)} kamera berjalan.")

    def berhenti(self) -> None:
        """Matikan pengawas dan semua kamera dengan rapi."""
        self._stop_pengawas.set()
        if self._pengawas is not None and self._pengawas.is_alive():
            self._pengawas.join(timeout=5.0)
        self._pengawas = None

        with self._lock:
            pekerja = list(self._workers.values())
            self._workers.clear()
        for w in pekerja:
            try:
                w.stop()
            except Exception as e:
                logger.warning(f"[manajer] Gagal menghentikan '{w.profil.id}': {e}")
        logger.info("[manajer] Sistem produksi berhenti.")

    # ── Kendali per kamera ────────────────────────────────────────────────────
    def mulai_kamera(self, camera_id: str) -> CameraWorker:
        with self._lock:
            lama = self._workers.get(camera_id)
            if lama is not None and lama.is_alive():
                return lama

            profil = self.store.ambil(camera_id)
            if profil is None:
                raise KeyError(camera_id)

            w = CameraWorker(
                profil=profil,
                mesin_alert=self.alert,
                fall_model=self._fall_model,
                inter_model=self._inter_model,
                kunci_inferensi=self._kunci_inferensi,
            )
            self._workers[camera_id] = w
            w.start()
            return w

    def hentikan_kamera(self, camera_id: str) -> None:
        with self._lock:
            w = self._workers.pop(camera_id, None)
        if w is not None:
            w.stop()

    def mulai_ulang_kamera(self, camera_id: str) -> CameraWorker:
        """Wajib dipanggil setelah profil berubah — pekerja membaca profil sekali saat dibuat."""
        self.hentikan_kamera(camera_id)
        return self.mulai_kamera(camera_id)

    def berjalan(self, camera_id: str) -> bool:
        with self._lock:
            w = self._workers.get(camera_id)
        return bool(w and w.is_alive())

    def pekerja(self, camera_id: str) -> CameraWorker | None:
        with self._lock:
            return self._workers.get(camera_id)

    # ── CRUD profil (menjaga pekerja tetap sinkron dengan profil) ─────────────
    def tambah_kamera(self, data: dict) -> CameraProfile:
        profil = CameraProfile.from_dict(data)
        self.store.tambah(profil)
        if profil.aktif:
            self.mulai_kamera(profil.id)
        return profil

    def perbarui_kamera(self, camera_id: str, perubahan: dict) -> CameraProfile:
        profil = self.store.perbarui(camera_id, perubahan)
        # Profil dibaca sekali saat pekerja dibuat, jadi perubahan apa pun
        # baru berlaku setelah pekerja dijalankan ulang.
        if self.berjalan(camera_id):
            if profil.aktif:
                self.mulai_ulang_kamera(camera_id)
            else:
                self.hentikan_kamera(camera_id)
        elif profil.aktif:
            self.mulai_kamera(camera_id)
        return profil

    def hapus_kamera(self, camera_id: str) -> None:
        self.hentikan_kamera(camera_id)
        self.store.hapus(camera_id)

    # ── Kesehatan ─────────────────────────────────────────────────────────────
    def kesehatan(self) -> dict:
        with self._lock:
            pekerja = dict(self._workers)

        daftar = []
        for p in self.store.semua():
            w = pekerja.get(p.id)
            if w is not None:
                daftar.append(w.kesehatan())
            else:
                daftar.append({
                    "kamera_id": p.id,
                    "nama": p.nama,
                    "jenis": p.jenis,
                    "berjalan": False,
                    "sumber": p.sumber_aman(),
                    "fall_aktif": p.run_fall and self._fall_model is not None,
                    "interaksi_aktif": p.run_interaction and self._inter_model is not None,
                })

        return {
            "kamera": daftar,
            "jumlah_kamera": len(daftar),
            "kamera_berjalan": sum(1 for d in daftar if d.get("berjalan")),
            "kamera_terhubung": sum(
                1 for d in daftar if d.get("stream", {}).get("terhubung")
            ),
            "model": {
                "fall_head": self._fall_model is not None,
                "interaction_head": self._inter_model is not None,
            },
            "alert": self.alert.statistik(),
            "kejadian": self.log.ringkasan(),
        }

    # ── Pengawas ──────────────────────────────────────────────────────────────
    def _loop_pengawas(self) -> None:
        while not self._stop_pengawas.is_set():
            if self._stop_pengawas.wait(self._interval_pengawas):
                break

            # 1. Nyalakan ulang pekerja yang mati tak terduga.
            try:
                with self._lock:
                    kandidat = [
                        (cid, w) for cid, w in self._workers.items() if not w.is_alive()
                    ]
                for cid, _ in kandidat:
                    profil = self.store.ambil(cid)
                    if profil is None or not profil.aktif:
                        continue
                    logger.warning(f"[pengawas] Pekerja '{cid}' mati — dinyalakan ulang.")
                    with self._lock:
                        self._workers.pop(cid, None)
                    self.mulai_kamera(cid)
            except Exception as e:
                logger.error(f"[pengawas] Gagal memulihkan pekerja: {e}")

            # 2. Retensi log kejadian + pembersihan state debounce (§7).
            try:
                sekarang = time.time()
                if sekarang - self._t_purge_terakhir >= 600.0:   # tiap 10 menit
                    self.log.buang_kedaluwarsa()
                    self.alert.bersihkan_debounce()
                    self._t_purge_terakhir = sekarang
            except Exception as e:
                logger.error(f"[pengawas] Gagal menjalankan retensi: {e}")

            # 3. Kabari dashboard soal kesehatan, agar operator tahu kamera mati
            #    tanpa harus menunggu alert yang tidak akan pernah datang.
            try:
                self.alert.siarkan_status({
                    "type": "kesehatan",
                    "t": time.time(),
                    "ringkas": {
                        "kamera_berjalan": sum(
                            1 for cid in list(self._workers) if self.berjalan(cid)
                        ),
                        "kamera_total": len(self.store.semua()),
                    },
                })
            except Exception:
                pass
